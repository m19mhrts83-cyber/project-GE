#!/usr/bin/env python3
"""611 AI 使用量の週次集計（ルールのみ・LLM なし）。

4者（Claude Code／Codex／Cursor／GenCode）＋ ChatGPT モードの使用量を 1 つの表にする。

取れるもの（Mac ローカルログ、2026-11-06 確認）:
  Claude Code : ~/.claude/projects/**/*.jsonl  … 応答ごとのトークン数・モデル・
                5時間枠／週次枠に当たった記録。プランの使用％は無い（手入力欄あり）
  Codex       : ~/.codex/sessions/**/*.jsonl（＋archived_sessions）… token_count
                イベントの累計トークンと、5時間枠・週次枠の使用％（rate_limits）
取れないもの（手入力）／別スクリプト:
  Cursor      : .jarvis_state/cursor_usage_watch.json を読む。値は jarvis_cursor_usage_fetch.py が
                ログイン済みブラウザから自動で入れる（失敗時は目視の手入力値のまま）
  GenCode     : 手入力欄（.jarvis_state/ai_usage_manual.json）
  ChatGPT モード: 手入力欄（同上）。チャットはローカルログが無い

本文・プロンプトは読まない／書かない。数えるのはトークン数と件数だけ。

  python3 scripts/jarvis_ai_usage_weekly.py                 # 直近7日の表を表示＋写しJSON保存
  python3 scripts/jarvis_ai_usage_weekly.py --dry-run --json
  python3 scripts/jarvis_ai_usage_weekly.py --set-manual gencode --pct 40 --note "Genspark画面"
  python3 scripts/jarvis_ai_usage_weekly.py --push          # 既存 metrics／sync_meta へ写す（スキーマ変更なし）

週次の起動は 314 の週次 runner（土 9:00 launchd）に相乗りする。専用スケジューラは作らない。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Iterator
from zoneinfo import ZoneInfo

JST = ZoneInfo("Asia/Tokyo")
REPO = Path(__file__).resolve().parents[1]
STATE_DIR = REPO / ".jarvis_state"
OUT_PATH = STATE_DIR / "ai_usage_weekly.json"
MANUAL_PATH = STATE_DIR / "ai_usage_manual.json"
CURSOR_PATH = STATE_DIR / "cursor_usage_watch.json"

HOME = Path.home()
CLAUDE_DIRS = [HOME / ".claude" / "projects"]
CODEX_DIRS = [HOME / ".codex" / "sessions", HOME / ".codex" / "archived_sessions"]

MANUAL_TOOLS = ("claude_plan", "gencode", "chatgpt_mode")
HISTORY_KEEP = 12  # 写しに残す週数

# 閾値（Cursor の既存ルールと同じ値）
WARN_PCT = 70.0
ASK_PCT = 90.0


# ------------------------------------------------------------------ 共通
def _parse_ts(s: Any) -> datetime | None:
    if not s or not isinstance(s, str):
        return None
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _iso(dt: datetime | None) -> str | None:
    return dt.astimezone(JST).isoformat(timespec="seconds") if dt else None


def _jsonl_files(dirs: Iterable[Path], since: datetime) -> Iterator[Path]:
    """更新日時が since より古いファイルは中身を読まない（窓の外）。"""
    floor = since.timestamp()
    for d in dirs:
        if not d.is_dir():
            continue
        for f in d.rglob("*.jsonl"):
            try:
                if f.stat().st_mtime >= floor:
                    yield f
            except OSError:
                continue


def _iter_json(path: Path) -> Iterator[dict[str, Any]]:
    try:
        with path.open(encoding="utf-8", errors="replace") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    d = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(d, dict):
                    yield d
    except OSError:
        return


def _int(v: Any) -> int:
    try:
        return int(v or 0)
    except (TypeError, ValueError):
        return 0


# ------------------------------------------------------------------ Claude Code
def summarize_claude(records: Iterable[dict[str, Any]], since: datetime, until: datetime) -> dict[str, Any]:
    """Claude Code の jsonl 行から集計する。同じ応答が複数行に分かれるので message.id で重複を除く。"""
    seen: set[str] = set()
    sessions: set[str] = set()
    by_model: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    tot: dict[str, int] = defaultdict(int)
    hits: list[dict[str, Any]] = []
    hit_keys: set[tuple] = set()
    entrypoints: dict[str, int] = defaultdict(int)

    for d in records:
        ts = _parse_ts(d.get("timestamp"))
        if not ts or ts < since or ts >= until:
            continue
        msg = d.get("message") if isinstance(d.get("message"), dict) else {}

        # 枠に当たった記録（apiError か、合成メッセージ「You've hit your ... limit」）
        kind = None
        params = d.get("apiErrorParams") or {}
        rli = params.get("rate_limit_info") if isinstance(params, dict) else None
        if d.get("apiError") == "usage_limit_reached" and isinstance(rli, dict):
            kind = rli.get("rateLimitType")
        elif msg.get("model") == "<synthetic>":
            for c in msg.get("content") or []:
                t = c.get("text", "") if isinstance(c, dict) else ""
                if "hit your 5-hour limit" in t:
                    kind = "five_hour"
                elif "hit your weekly limit" in t:
                    kind = "seven_day"
        if kind:
            key = (kind, ts.strftime("%Y-%m-%dT%H"))
            if key not in hit_keys:
                hit_keys.add(key)
                hits.append({"at": _iso(ts), "type": kind,
                             "resets_at": _iso(datetime.fromtimestamp(rli["resetsAt"], timezone.utc))
                             if isinstance(rli, dict) and rli.get("resetsAt") else None})

        if d.get("type") != "assistant" or msg.get("model") in (None, "<synthetic>"):
            continue
        usage = msg.get("usage")
        if not isinstance(usage, dict):
            continue
        mid = msg.get("id") or d.get("requestId") or d.get("uuid")
        if mid in seen:
            continue
        seen.add(mid)
        if d.get("sessionId"):
            sessions.add(d["sessionId"])
        entrypoints[str(d.get("entrypoint") or "unknown")] += 1
        row = {
            "input": _int(usage.get("input_tokens")),
            "output": _int(usage.get("output_tokens")),
            "cache_write": _int(usage.get("cache_creation_input_tokens")),
            "cache_read": _int(usage.get("cache_read_input_tokens")),
        }
        m = by_model[str(msg.get("model"))]
        m["requests"] += 1
        tot["requests"] += 1
        for k, v in row.items():
            m[k] += v
            tot[k] += v

    hits.sort(key=lambda x: x["at"])
    return {
        "source": "local_log",
        "available": True,
        "sessions": len(sessions),
        "requests": tot["requests"],
        "tokens": {k: tot[k] for k in ("input", "output", "cache_write", "cache_read")},
        "by_model": {k: dict(v) for k, v in sorted(by_model.items())},
        "by_entrypoint": dict(entrypoints),
        "limit_hits": hits,
        "plan_pct": None,  # ローカルログに使用％は無い。手入力（claude_plan）で補う
        "coverage": "この Mac の Claude Code（CLI・デスクトップ）だけ。claude.ai のチャットとクラウド実行は含まない",
    }


def collect_claude(since: datetime, until: datetime) -> dict[str, Any]:
    files = list(_jsonl_files(CLAUDE_DIRS, since))
    if not any(d.is_dir() for d in CLAUDE_DIRS):
        return {"source": "local_log", "available": False, "reason": "~/.claude/projects が無い"}

    def gen():
        for f in files:
            yield from _iter_json(f)

    out = summarize_claude(gen(), since, until)
    out["files_scanned"] = len(files)
    return out


# ------------------------------------------------------------------ Codex
def summarize_codex_session(records: Iterable[dict[str, Any]], since: datetime, until: datetime) -> dict[str, Any]:
    """1 セッション分。total_token_usage（累計）の差分を窓の中だけ足す。"""
    prev: dict[str, int] | None = None
    add: dict[str, int] = defaultdict(int)
    turns = 0
    limits: list[tuple[datetime, dict[str, Any]]] = []
    keys = ("input_tokens", "cached_input_tokens", "output_tokens", "reasoning_output_tokens", "total_tokens")
    for d in records:
        if d.get("type") != "event_msg":
            continue
        p = d.get("payload") or {}
        if p.get("type") != "token_count":
            continue
        ts = _parse_ts(d.get("timestamp"))
        if not ts:
            continue
        rl = p.get("rate_limits")
        if isinstance(rl, dict) and rl.get("limit_id") == "codex" and since <= ts < until:
            limits.append((ts, rl))
        info = p.get("info")
        if not isinstance(info, dict) or not isinstance(info.get("total_token_usage"), dict):
            continue
        cur = {k: _int(info["total_token_usage"].get(k)) for k in keys}
        if prev is None or cur["total_tokens"] < prev["total_tokens"]:
            # 最初の観測、または累計が戻った（再開等）→ 直近1回分だけを差分とみなす
            last = info.get("last_token_usage") or {}
            delta = {k: _int(last.get(k)) for k in keys}
        else:
            delta = {k: cur[k] - prev[k] for k in keys}
        prev = cur
        if since <= ts < until and delta["total_tokens"] > 0:
            turns += 1
            for k in keys:
                add[k] += delta[k]
    return {"tokens": dict(add), "turns": turns, "limits": limits}


def _limit_view(w: Any) -> dict[str, Any] | None:
    if not isinstance(w, dict):
        return None
    ra = w.get("resets_at")
    return {
        "used_pct": w.get("used_percent"),
        "window_minutes": w.get("window_minutes"),
        "resets_at": _iso(datetime.fromtimestamp(ra, timezone.utc)) if ra else None,
    }


def collect_codex(since: datetime, until: datetime) -> dict[str, Any]:
    if not any(d.is_dir() for d in CODEX_DIRS):
        return {"source": "local_log", "available": False, "reason": "~/.codex/sessions が無い"}
    tot: dict[str, int] = defaultdict(int)
    sessions = 0
    turns = 0
    limits: list[tuple[datetime, dict[str, Any]]] = []
    files = list(_jsonl_files(CODEX_DIRS, since))
    for f in files:
        s = summarize_codex_session(_iter_json(f), since, until)
        if s["turns"]:
            sessions += 1
            turns += s["turns"]
            for k, v in s["tokens"].items():
                tot[k] += v
        limits.extend(s["limits"])
    return {"source": "local_log", "available": True, "files_scanned": len(files),
            **summarize_codex_limits(limits),
            "sessions": sessions, "turns": turns,
            "tokens": {
                "input": tot["input_tokens"], "cached_input": tot["cached_input_tokens"],
                "output": tot["output_tokens"], "reasoning_output": tot["reasoning_output_tokens"],
                "total": tot["total_tokens"],
            },
            "coverage": "この Mac の Codex（CLI・デスクトップ）。ChatGPT のチャットは含まない"}


def summarize_codex_limits(limits: list[tuple[datetime, dict[str, Any]]]) -> dict[str, Any]:
    if not limits:
        return {"limits_latest": None, "weekly_pct_max": None, "five_hour_pct_max": None, "plan_type": None}
    limits.sort(key=lambda x: x[0])
    ts, rl = limits[-1]

    def mx(name: str) -> float | None:
        vals = [r.get(name, {}).get("used_percent") for _, r in limits if isinstance(r.get(name), dict)]
        vals = [v for v in vals if isinstance(v, (int, float))]
        return max(vals) if vals else None

    return {
        "limits_latest": {"at": _iso(ts), "five_hour": _limit_view(rl.get("primary")),
                          "weekly": _limit_view(rl.get("secondary"))},
        "weekly_pct_max": mx("secondary"),
        "five_hour_pct_max": mx("primary"),
        "plan_type": rl.get("plan_type"),
    }


# ------------------------------------------------------------------ 手入力・Cursor
def load_json(path: Path) -> dict[str, Any]:
    try:
        d = json.loads(path.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def save_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _max_pct(*vals: Any) -> float | None:
    nums = [float(v) for v in vals if isinstance(v, (int, float))]
    return max(nums) if nums else None


def collect_cursor() -> dict[str, Any]:
    st = load_json(CURSOR_PATH)
    if not st:
        return {"source": "manual", "available": False, "reason": "cursor_usage_watch.json が無い"}
    try:
        sys.path.insert(0, str(REPO / "scripts"))
        import jarvis_cursor_usage_watch as cw  # noqa: E402
        st = cw.evaluate(st)
    except Exception:  # 評価できなくても値は写す
        pass
    return {
        "source": "manual", "available": True,
        "plan": st.get("plan"),
        # Pro の枠は Cursor Models（auto）と Other（API）の2本。逼迫している方で見る
        "pct": _max_pct(st.get("cursor_models_pct_used"), st.get("other_models_pct_used")),
        "cursor_models_pct": st.get("cursor_models_pct_used"),
        "other_models_pct": st.get("other_models_pct_used"),
        "total_pct": st.get("total_pct_used"),
        "grok_bot_weekly_pct": st.get("grok_bot_weekly_pct"),
        "grok_bot_resets_at": st.get("grok_bot_resets_at"),
        "fetch_source": st.get("fetch_source") or "manual",
        "auto_fetched_at": st.get("auto_fetched_at"),
        "updated_at": st.get("updated_at"),
        "level": st.get("level"), "verdict": st.get("verdict"),
    }


def collect_manual(tool: str) -> dict[str, Any]:
    e = (load_json(MANUAL_PATH).get(tool) or {})
    return {"source": "manual", "available": e.get("pct") is not None,
            "pct": e.get("pct"), "updated_at": e.get("updated_at"), "note": e.get("note")}


def set_manual(tool: str, pct: float | None, note: str | None) -> dict[str, Any]:
    data = load_json(MANUAL_PATH)
    e = dict(data.get(tool) or {})
    if pct is not None:
        e["pct"] = max(0.0, min(100.0, float(pct)))
    if note is not None:
        e["note"] = note
    e["updated_at"] = datetime.now(JST).isoformat(timespec="seconds")
    data[tool] = e
    save_json(MANUAL_PATH, data)
    return e


# ------------------------------------------------------------------ 判定・表
def level_for(pct: Any) -> str:
    if not isinstance(pct, (int, float)):
        return "unknown"
    if pct >= ASK_PCT:
        return "attention"
    if pct >= WARN_PCT:
        return "warn"
    return "ok"


def build_rows(rep: dict[str, Any]) -> list[dict[str, Any]]:
    t = rep["tools"]
    cl, cx, cu = t["claude_code"], t["codex"], t["cursor"]
    claude_pct = t["claude_plan"].get("pct")
    cx_week = ((cx.get("limits_latest") or {}).get("weekly") or {}).get("used_pct")
    rows = [
        {"tool": "Claude Code（ミスレモン）", "auto": "取れる（トークン）／％は手入力",
         "pct": claude_pct, "pct_src": "手入力" if claude_pct is not None else "—",
         "volume": f"{cl.get('requests', 0)}応答・出力{cl.get('tokens', {}).get('output', 0):,}tok"
         if cl.get("available") else "—",
         "hits": len(cl.get("limit_hits") or [])},
        {"tool": "Codex", "auto": "取れる（トークン＋5h/週次％）",
         "pct": cx_week, "pct_src": "ログ" if cx_week is not None else "—",
         "volume": f"{cx.get('turns', 0)}ターン・出力{cx.get('tokens', {}).get('output', 0):,}tok"
         if cx.get("available") else "—",
         "hits": None},
        {"tool": "Cursor（ジャービス）", "auto": "取れる（ログイン済みブラウザ）／失敗時は手入力",
         "pct": cu.get("pct"),
         "pct_src": ("自動" if cu.get("fetch_source") == "auto" else "手入力")
         if cu.get("pct") is not None else "—",
         "volume": "—", "hits": None},
        {"tool": "Grok Bot（Cursor 内・週次）", "auto": "取れる（ログイン済みブラウザ）",
         "pct": cu.get("grok_bot_weekly_pct"),
         "pct_src": ("自動" if cu.get("fetch_source") == "auto" else "手入力")
         if cu.get("grok_bot_weekly_pct") is not None else "—",
         "volume": f"リセット {cu.get('grok_bot_resets_at')}" if cu.get("grok_bot_resets_at") else "—",
         "hits": None},
        {"tool": "GenCode（フライデー）", "auto": "取れない（手入力）",
         "pct": t["gencode"].get("pct"), "pct_src": "手入力" if t["gencode"].get("pct") is not None else "—",
         "volume": "—", "hits": None},
        {"tool": "ChatGPT モード（チャッピー）", "auto": "取れない（手入力）",
         "pct": t["chatgpt_mode"].get("pct"),
         "pct_src": "手入力" if t["chatgpt_mode"].get("pct") is not None else "—",
         "volume": "—", "hits": None},
    ]
    for r in rows:
        r["level"] = level_for(r["pct"])
    return rows


def render_md(rep: dict[str, Any]) -> str:
    lines = [f"### AI 使用量（{rep['period']['since'][:10]}〜{rep['period']['until'][:10]}）", "",
             "| ツール | 自動取得 | 週次％ | 出所 | 量（窓内） | 判定 |", "|---|---|---|---|---|---|"]
    for r in rep["rows"]:
        pct = f"{r['pct']:.0f}%" if isinstance(r["pct"], (int, float)) else "—"
        vol = r["volume"] + (f"・枠到達{r['hits']}回" if r.get("hits") else "")
        lines.append(f"| {r['tool']} | {r['auto']} | {pct} | {r['pct_src']} | {vol} | {r['level']} |")
    cx = rep["tools"]["codex"].get("limits_latest") or {}
    if cx:
        w, f = cx.get("weekly") or {}, cx.get("five_hour") or {}
        lines += ["", f"- Codex 最新（{cx.get('at')}）: 5h {f.get('used_pct')}% / 週 {w.get('used_pct')}%"
                      f"（週リセット {w.get('resets_at')}）",
                  f"- Codex 窓内の最大: 5h {rep['tools']['codex'].get('five_hour_pct_max')}% / "
                  f"週 {rep['tools']['codex'].get('weekly_pct_max')}%"]
    for h in rep["tools"]["claude_code"].get("limit_hits") or []:
        lines.append(f"- Claude 枠到達: {h['at']} {h['type']}（リセット {h.get('resets_at') or '—'}）")
    return "\n".join(lines)


def build_report(days: int, now: datetime | None = None) -> dict[str, Any]:
    until = (now or datetime.now(JST)).astimezone(timezone.utc)
    since = until - timedelta(days=days)
    rep = {
        "generated_at": _iso(until),
        "period": {"since": _iso(since), "until": _iso(until), "days": days},
        "tools": {
            "claude_code": collect_claude(since, until),
            "codex": collect_codex(since, until),
            "cursor": collect_cursor(),
            "claude_plan": collect_manual("claude_plan"),
            "gencode": collect_manual("gencode"),
            "chatgpt_mode": collect_manual("chatgpt_mode"),
        },
        "llm_used": False,
    }
    rep["rows"] = build_rows(rep)
    return rep


def save_copy(rep: dict[str, Any]) -> None:
    """写し（正本は Supabase 予定）。週ごとに積み、直近 HISTORY_KEEP 件だけ残す。"""
    data = load_json(OUT_PATH)
    hist = [h for h in data.get("history") or [] if h.get("period", {}).get("until", "")[:10]
            != rep["period"]["until"][:10]]
    hist.append(rep)
    hist.sort(key=lambda h: h.get("period", {}).get("until", ""))
    save_json(OUT_PATH, {"latest": rep, "history": hist[-HISTORY_KEEP:]})


TOOL_ENTITY = {"claude_code": "claude_code", "codex": "codex", "cursor": "cursor",
               "gencode": "gencode", "chatgpt_mode": "chatgpt_mode", "grok_bot": "grok_bot"}


def metric_rows(rep: dict[str, Any]) -> list[dict[str, Any]]:
    """既存 metrics（metric, entity, recorded_at で一意）に載せる行。スキーマ変更なし。"""
    day = rep["period"]["until"][:10]
    t = rep["tools"]
    base = {"period": rep["period"]}
    rows: list[dict[str, Any]] = []

    def add(metric: str, entity: str, value: Any, unit: str, payload: dict[str, Any] | None = None):
        if isinstance(value, (int, float)):
            rows.append({"metric": metric, "entity": entity, "value": float(value), "unit": unit,
                         "recorded_at": day, "payload": {**base, **(payload or {})}})

    pcts = {
        "claude_code": (t["claude_plan"].get("pct"), "manual"),
        "codex": (((t["codex"].get("limits_latest") or {}).get("weekly") or {}).get("used_pct"), "local_log"),
        "cursor": (t["cursor"].get("pct"), t["cursor"].get("fetch_source") or "manual"),
        "gencode": (t["gencode"].get("pct"), "manual"),
        "chatgpt_mode": (t["chatgpt_mode"].get("pct"), "manual"),
    }
    pcts["grok_bot"] = (t["cursor"].get("grok_bot_weekly_pct"), t["cursor"].get("fetch_source") or "manual")
    for tool, (pct, src) in pcts.items():
        add("ai_usage_weekly_pct", TOOL_ENTITY[tool], pct, "pct", {"source": src})
    cx, cl = t["codex"], t["claude_code"]
    if cx.get("available"):
        add("ai_usage_weekly_pct_max", "codex", cx.get("weekly_pct_max"), "pct", {"source": "local_log"})
        add("ai_usage_output_tokens", "codex", (cx.get("tokens") or {}).get("output"), "tokens",
            {"tokens": cx.get("tokens"), "sessions": cx.get("sessions")})
        add("ai_usage_requests", "codex", cx.get("turns"), "turns")
    if cl.get("available"):
        add("ai_usage_output_tokens", "claude_code", (cl.get("tokens") or {}).get("output"), "tokens",
            {"tokens": cl.get("tokens"), "by_model": cl.get("by_model"), "sessions": cl.get("sessions")})
        add("ai_usage_requests", "claude_code", cl.get("requests"), "responses")
        add("ai_usage_limit_hits", "claude_code", len(cl.get("limit_hits") or []), "count",
            {"limit_hits": cl.get("limit_hits")})
    return rows


def push_supabase(rep: dict[str, Any]) -> bool:
    """既存テーブルだけを使う: metrics に週次の数値、sync_meta に最新の全体 JSON。"""
    url = (os.environ.get("JARVIS_SUPABASE_URL") or "").strip()
    key = (os.environ.get("JARVIS_SUPABASE_SERVICE_ROLE_KEY") or "").strip()
    if not url or not key:
        print("# supabase skip: JARVIS_SUPABASE_* 未設定", file=sys.stderr)
        return False
    try:
        from supabase import create_client
        sb = create_client(url, key)
        rows = metric_rows(rep)
        if rows:
            sb.table("metrics").upsert(rows, on_conflict="metric,entity,recorded_at").execute()
        sb.table("sync_meta").upsert(
            {"key": "ai_usage_weekly", "value": json.dumps(rep, ensure_ascii=False),
             "updated_at": rep["generated_at"]}, on_conflict="key").execute()
        print(f"# supabase metrics rows={len(rows)}", file=sys.stderr)
        return True
    except Exception as e:
        print(f"# supabase skip: {e}", file=sys.stderr)
        return False


def main() -> int:
    ap = argparse.ArgumentParser(description="611 AI 使用量の週次集計")
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--dry-run", action="store_true", help="写し JSON を保存しない")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--push", action="store_true", help="Supabase の既存 metrics／sync_meta へ写す")
    ap.add_argument("--set-manual", choices=MANUAL_TOOLS, dest="set_manual")
    ap.add_argument("--pct", type=float)
    ap.add_argument("--note")
    args = ap.parse_args()

    if args.set_manual:
        if args.pct is None and args.note is None:
            print("--set-manual には --pct か --note が要る", file=sys.stderr)
            return 2
        print(json.dumps(set_manual(args.set_manual, args.pct, args.note), ensure_ascii=False))
        return 0

    rep = build_report(args.days)
    if not args.dry_run:
        save_copy(rep)
        print(f"# saved {OUT_PATH}", file=sys.stderr)
    if args.push:
        print(f"# push {'ok' if push_supabase(rep) else 'failed'}", file=sys.stderr)
    print(json.dumps(rep, ensure_ascii=False, indent=2) if args.json else render_md(rep))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
