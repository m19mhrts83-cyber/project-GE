#!/usr/bin/env python3
"""611 AI 使用量の「いまの値」と判断の目安をダッシュボードへ写す（ルールのみ・LLM なし）。

`ai-usage`（scripts/ai_usage_cli.py）が読む4者の枠を1回読み、
  1. 枠ごとの使用率・回復時刻・値の古さ
  2. 枠ごとの「その週（月）の最大値」の履歴
  3. プランを上げ下げする判断の目安（このペースで枠の何割まで行くか）
を sync_meta の `ai_usage_now` に写す。画面は Jarvis Dashboard の /ai-usage。

  python3 scripts/jarvis_ai_usage_snapshot.py            # 表示だけ
  python3 scripts/jarvis_ai_usage_snapshot.py --push     # 履歴を更新して Supabase へ写す
  python3 scripts/jarvis_ai_usage_snapshot.py --set-claude --weekly 50 --weekly-reset 2026-11-24T22:00:00Z \
      --five-hour 30 --five-hour-reset 2026-11-22T15:20:00Z   # Claude の値を手で入れる

Claude の値は statusLine（対話型の Claude Code）が保存する。デスクトップアプリだけを使う日は
保存されないので、アプリの「使用量」の数字を --set-claude で入れる（同じファイルへ書く）。

履歴は ~/.local/state/ai-usage/history.json（worktree をまたいで1つ）。秘密は出力しない。
目安の数字（MAX_TO_PRO・PRO_OK_BELOW）は Miss Lemon の案で、本人の確定基準ではない。画面にもそう出す。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ai_usage_cli as cli  # noqa: E402

STATE_DIR = Path(os.path.expanduser("~/.local/state/ai-usage"))
CLAUDE_PATH = STATE_DIR / "claude.json"
HISTORY_PATH = STATE_DIR / "history.json"
SYNC_KEY = "ai_usage_now"

HISTORY_KEEP = 16
WEEK_SEC = 7 * 86400
MONTH_SEC = 30 * 86400
MIN_ELAPSED = 0.15  # 枠の始めすぎる時は、ペースを出さない

# 目安（Miss Lemon の案。本人の確定基準ではない）
MAX_TO_PRO = 5.0      # Claude Max は Pro の約5倍、という前提
PRO_OK_BELOW = 20.0   # Max の週枠がこの％未満なら Pro に収まる（100 / MAX_TO_PRO）
NEAR_LIMIT = 90.0
WEEKS_NEEDED = 2      # この週数続いたら移行を提案する

AGENT_LABEL = {"claude": "Claude", "codex": "Codex（ChatGPT）", "cursor": "Cursor", "antigravity": "Antigravity"}
WINDOW_LABEL = {"five_hour": "5時間枠", "weekly": "週枠", "monthly": "月枠", "session": "5時間枠"}
PERIOD = {"weekly": WEEK_SEC, "monthly": MONTH_SEC}


def iso(ts: float | None) -> str | None:
    return None if ts is None else datetime.fromtimestamp(float(ts), timezone.utc).isoformat(timespec="seconds")


def parse_iso(s: str) -> float:
    return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()


# ------------------------------------------------------------------ 読む
def collect(now: float) -> dict[str, Any]:
    return {
        "claude": cli._safe(lambda: read_claude_all(now)),
        "codex": cli._safe(lambda: cli.read_codex(now)),
        "cursor": cli._safe(lambda: {"monthly": cli.read_cursor(), "age_min": 0}),
        "antigravity": cli._safe(cli.read_antigravity),
    }


def read_claude_all(now: float, path: Path | None = None) -> dict[str, Any]:
    """ai-usage と同じ値に、モデル別の週枠（あれば）を足す。"""
    out = cli.read_claude(now, str(path or CLAUDE_PATH))
    if "error" in out:
        return out
    try:
        rl = json.loads(Path(path or CLAUDE_PATH).read_text(encoding="utf-8")).get("rate_limits") or {}
    except Exception:
        rl = {}
    extra = []
    for key, w in rl.items():
        if key in ("five_hour", "seven_day") or not isinstance(w, dict):
            continue
        pct = w.get("used_percentage", w.get("used_percent"))
        if pct is None:
            continue
        extra.append({"key": key, "label": w.get("label") or key, "used_percent": pct, "resets_at_ts": w.get("resets_at")})
    if extra:
        out["extra"] = extra
    return out


def normalize(raw: dict[str, Any], now: float) -> list[dict[str, Any]]:
    """4者ばらばらの形を、枠1つ＝1行にそろえる。読めない所は error の行にする。"""
    rows: list[dict[str, Any]] = []

    def add(agent: str, window: str, label: str, w: dict[str, Any], age_min: Any, note: str | None = None):
        pct, rts = w.get("used_percent"), w.get("resets_at_ts")
        age = None if age_min is None else int(age_min)
        rows.append({
            "agent": agent, "agent_label": AGENT_LABEL.get(agent, agent), "window": window, "label": label,
            "used_percent": None if pct is None else float(pct),
            "resets_at": iso(rts) if rts else None,
            "observed_at": None if age is None else iso(now - age * 60),
            "age_min": age,
            "stale": age is None or age > cli.STALE_MIN,
            "reset_passed": bool(rts and float(rts) <= now),
            "note": note,
        })

    for agent, v in raw.items():
        if not isinstance(v, dict) or "error" in v:
            rows.append({"agent": agent, "agent_label": AGENT_LABEL.get(agent, agent), "window": "error", "label": "読めない",
                         "used_percent": None, "resets_at": None, "observed_at": None, "age_min": None,
                         "stale": True, "reset_passed": False, "note": (v or {}).get("error") if isinstance(v, dict) else None})
            continue
        if "buckets" in v:
            short = {"Gemini Models": "Gemini", "Claude and GPT models": "Claude/GPT"}
            for b in v["buckets"]:
                g = short.get(b.get("group"), b.get("group") or "")
                add(agent, f"{b.get('window')}:{g}", f"{g} {WINDOW_LABEL.get(b.get('window'), b.get('window'))}", b, v.get("age_min", 0))
            continue
        if "monthly" in v:
            add(agent, "monthly", "月枠", v["monthly"], v.get("age_min", 0), v["monthly"].get("message"))
            continue
        for key in ("five_hour", "weekly"):
            if key in v:
                add(agent, key, WINDOW_LABEL[key], v[key], v.get("age_min"))
        for e in v.get("extra") or []:
            add(agent, f"weekly:{e['key']}", f"週枠（{e['label']}）", e, v.get("age_min"))
        if v.get("limited"):
            rows.append({"agent": agent, "agent_label": AGENT_LABEL.get(agent, agent), "window": "limit_error",
                         "label": "使用量制限エラー", "used_percent": 100.0, "resets_at": None,
                         "observed_at": iso(now - int(v.get("age_min") or 0) * 60), "age_min": v.get("age_min"),
                         "stale": False, "reset_passed": False,
                         "note": f"回復目安 {(v.get('limit_error') or {}).get('retry') or '不明'}"})
    return rows


# ------------------------------------------------------------------ 履歴（週・月ごとの最大値）
def update_history(history: dict[str, list[dict[str, Any]]], rows: list[dict[str, Any]], now: float) -> dict[str, list[dict[str, Any]]]:
    """新しい値だけを足す。古い値・回復時刻を過ぎた値は、どの週の値か分からないので足さない。"""
    out = {k: [dict(e) for e in v] for k, v in history.items()}
    for r in rows:
        base = r["window"].split(":")[0]
        if base not in PERIOD or r["used_percent"] is None or r["stale"] or r["reset_passed"] or not r["resets_at"]:
            continue
        key = f"{r['agent']}.{r['window']}"
        wid = round(parse_iso(r["resets_at"]) / 3600) * 3600  # 回復時刻（1時間に丸め）がその枠の名前
        lst = out.setdefault(key, [])
        hit = next((e for e in lst if abs(e["resets_at_ts"] - wid) <= 3600), None)
        if hit is None:
            lst.append({"resets_at_ts": wid, "peak": r["used_percent"], "seen_at": r["observed_at"]})
        elif r["used_percent"] >= hit["peak"]:
            hit["peak"], hit["seen_at"] = r["used_percent"], r["observed_at"]
        lst.sort(key=lambda e: e["resets_at_ts"])
        del lst[:-HISTORY_KEEP]
    return out


# ------------------------------------------------------------------ 判断の目安
def pace(used: float, resets_at_ts: float, period: float, now: float) -> float | None:
    """このペースのまま枠の終わりまで行った時の使用率（％）。枠の始めすぎる時は None。"""
    elapsed = 1 - (resets_at_ts - now) / period
    if elapsed < MIN_ELAPSED:
        return None
    return round(used / min(elapsed, 1.0), 1)


def _row(rows: list[dict[str, Any]], agent: str, window: str) -> dict[str, Any] | None:
    return next((r for r in rows if r["agent"] == agent and r["window"] == window), None)


def judge(rows: list[dict[str, Any]], history: dict[str, list[dict[str, Any]]], now: float) -> list[dict[str, Any]]:
    """level: ok（余裕）/ keep（今のプランが要る）/ warn（上限に近い・制限中）/ unknown（判断できない）。"""
    out: list[dict[str, Any]] = []

    def usable(r: dict[str, Any] | None) -> bool:
        return bool(r and r["used_percent"] is not None and not r["stale"] and not r["reset_passed"] and r["resets_at"])

    # Claude: Max を続けるか、Pro に下げられるか
    c = _row(rows, "claude", "weekly")
    done = [e for e in history.get("claude.weekly", []) if e["resets_at_ts"] <= now]
    streak = 0
    for e in reversed(done):
        if e["peak"] < PRO_OK_BELOW:
            streak += 1
        else:
            break
    if not usable(c):
        out.append({"agent": "claude", "level": "unknown", "title": "Claude：値が古く、判断できません",
                    "detail": "アプリの 設定→使用量 の数字を入れると更新されます。", "pace_percent": None,
                    "pro_multiple": None, "streak_weeks": streak})
    else:
        p = pace(c["used_percent"], parse_iso(c["resets_at"]), WEEK_SEC, now)
        ref = p if p is not None else c["used_percent"]
        mult = round(ref * MAX_TO_PRO / 100, 1)
        if ref >= NEAR_LIMIT:
            level, title = "warn", "Claude：Max の上限に近いペースです"
        elif ref >= PRO_OK_BELOW:
            level, title = "keep", f"Claude：Max が要ります（Pro の約{mult:g}倍のペース）"
        else:
            level, title = "ok", "Claude：今週は Pro に収まるペースです"
        detail = (f"週枠 {c['used_percent']:g}% 使用。" +
                  (f"このペースだと枠の終わりに約{p:g}%。" if p is not None else "週の始めのため、ペースはまだ出しません。") +
                  f"Pro に収まった週は連続 {streak} 週（{WEEKS_NEEDED} 週で移行を提案）。")
        out.append({"agent": "claude", "level": level, "title": title, "detail": detail,
                    "pace_percent": p, "pro_multiple": mult, "streak_weeks": streak})

    # Cursor: Pro で足りるか
    u = _row(rows, "cursor", "monthly")
    if not usable(u):
        out.append({"agent": "cursor", "level": "unknown", "title": "Cursor：値が読めず、判断できません",
                    "detail": (u or {}).get("note") or "cursor-agent のログインを確かめてください。", "pace_percent": None})
    else:
        p = pace(u["used_percent"], parse_iso(u["resets_at"]), MONTH_SEC, now)
        if u["used_percent"] >= 100:
            level, title = "warn", "Cursor：月の枠を使い切り、制限中です"
        elif (p or 0) >= 100:
            level, title = "warn", "Cursor：このペースだと月の途中で止まります"
        elif u["used_percent"] >= 70 or (p or 0) >= 70:
            level, title = "keep", "Cursor：今のプランでぎりぎり収まるペースです"
        else:
            level, title = "ok", "Cursor：今のプランで余裕があります"
        out.append({"agent": "cursor", "level": level, "title": title,
                    "detail": f"月枠 {u['used_percent']:g}% 使用。" + (f"このペースだと月末に約{p:g}%。" if p is not None else ""),
                    "pace_percent": p})

    # Codex: 週枠
    x = _row(rows, "codex", "weekly")
    limited = _row(rows, "codex", "limit_error")
    if limited:
        out.append({"agent": "codex", "level": "warn", "title": "Codex：使用量の制限に当たっています",
                    "detail": limited.get("note") or "", "pace_percent": None})
    elif not usable(x):
        out.append({"agent": "codex", "level": "unknown", "title": "Codex：値が古く、判断できません",
                    "detail": "Codex を一度動かすと更新されます。", "pace_percent": None})
    else:
        p = pace(x["used_percent"], parse_iso(x["resets_at"]), WEEK_SEC, now)
        ref = p if p is not None else x["used_percent"]
        level, title = (("warn", "Codex：週の上限に近いペースです") if ref >= NEAR_LIMIT else
                        ("keep", "Codex：週枠をよく使っています") if ref >= 70 else
                        ("ok", "Codex：週枠に余裕があります"))
        out.append({"agent": "codex", "level": level, "title": title,
                    "detail": f"週枠 {x['used_percent']:g}% 使用。" + (f"このペースだと枠の終わりに約{p:g}%。" if p is not None else ""),
                    "pace_percent": p})
    return out


def build(raw: dict[str, Any], history: dict[str, list[dict[str, Any]]], now: float) -> dict[str, Any]:
    rows = normalize(raw, now)
    hist = update_history(history, rows, now)
    return {
        "generated_at": iso(now),
        "rows": rows,
        "verdicts": judge(rows, hist, now),
        "history": {k: [{"resets_at": iso(e["resets_at_ts"]), "peak": e["peak"], "seen_at": e.get("seen_at"),
                         "closed": e["resets_at_ts"] <= now} for e in v] for k, v in hist.items()},
        "assumptions": {"max_to_pro": MAX_TO_PRO, "pro_ok_below": PRO_OK_BELOW, "weeks_needed": WEEKS_NEEDED,
                        "near_limit": NEAR_LIMIT, "stale_min": cli.STALE_MIN, "status": "proposal"},
        "_history_raw": hist,
    }


# ------------------------------------------------------------------ 保存・写す
def load_history(path: Path = HISTORY_PATH) -> dict[str, list[dict[str, Any]]]:
    try:
        d = json.loads(path.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except FileNotFoundError:
        return {}


def save_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(path)


def set_claude(args: argparse.Namespace, now: float, path: Path = CLAUDE_PATH) -> dict[str, Any]:
    """アプリの使用量の数字を、statusLine と同じ形で保存する（ai-usage もこれを読む）。"""
    rl: dict[str, Any] = {}
    if args.weekly is not None:
        rl["seven_day"] = {"used_percentage": args.weekly, "resets_at": parse_iso(args.weekly_reset) if args.weekly_reset else None}
    if args.five_hour is not None:
        rl["five_hour"] = {"used_percentage": args.five_hour, "resets_at": parse_iso(args.five_hour_reset) if args.five_hour_reset else None}
    if args.model_weekly is not None:
        rl["seven_day_model"] = {"used_percentage": args.model_weekly, "label": args.model_label or "モデル別",
                                 "resets_at": parse_iso(args.weekly_reset) if args.weekly_reset else None}
    if "seven_day" not in rl:
        raise SystemExit("--set-claude には --weekly が要ります")
    data = {"saved_at": int(now), "source": "app_usage", "rate_limits": rl}
    save_json(path, data)
    return data


def push(rep: dict[str, Any]) -> bool:
    url = (os.environ.get("JARVIS_SUPABASE_URL") or "").strip()
    key = (os.environ.get("JARVIS_SUPABASE_SERVICE_ROLE_KEY") or "").strip()
    if not url or not key:
        print("# supabase skip: JARVIS_SUPABASE_* 未設定", file=sys.stderr)
        return False
    try:
        from supabase import create_client
        create_client(url, key).table("sync_meta").upsert(
            {"key": SYNC_KEY, "value": json.dumps(rep, ensure_ascii=False), "updated_at": rep["generated_at"]},
            on_conflict="key").execute()
        return True
    except Exception as e:
        print(f"# supabase skip: {type(e).__name__}: {e}"[:200], file=sys.stderr)
        return False


def render(rep: dict[str, Any]) -> str:
    lines = [f"AI 使用量（{rep['generated_at']}）"]
    for v in rep["verdicts"]:
        lines.append(f"- {v['title']}　{v['detail']}")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--push", action="store_true", help="履歴を更新して sync_meta へ写す")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--set-claude", action="store_true", help="Claude の値を手で入れる")
    ap.add_argument("--weekly", type=float)
    ap.add_argument("--weekly-reset")
    ap.add_argument("--five-hour", type=float)
    ap.add_argument("--five-hour-reset")
    ap.add_argument("--model-weekly", type=float)
    ap.add_argument("--model-label")
    args = ap.parse_args()

    now = time.time()
    if args.set_claude:
        set_claude(args, now)
    rep = build(collect(now), load_history(), now)
    hist = rep.pop("_history_raw")
    ok = True
    if args.push:
        save_json(HISTORY_PATH, hist)
        ok = push(rep)
    print(json.dumps(rep, ensure_ascii=False, indent=1) if args.json else render(rep))
    if args.push:
        print(f"# push: {'ok' if ok else '失敗（保存だけした）'}", file=sys.stderr)
    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
