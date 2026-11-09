#!/usr/bin/env python3
"""611 配車案（動きB）— 作業ごとに「このエージェントで」の割り振り案を作る（ルールのみ・LLM なし）。

入力: 作業（社員フォルダの TASK.md を1件以上、または --title の手入力）＋ 使用量（その場で集計・書き込みなし）
出力: #consult 向けの文面（番号付きのまとめ＋各件の「そのまま貼る依頼文」）。
      既定はファイルに書くだけ（dry-run）。--post を付けたときだけ Webhook 投稿。

  python3 scripts/jarvis_ai_dispatch_suggest.py --task docs/.../111_.../TASK.md docs/.../317_.../TASK.md
  python3 scripts/jarvis_ai_dispatch_suggest.py --title "814 点検を画面別判定に" --kind implement
  python3 scripts/jarvis_ai_dispatch_suggest.py --task ... --post   # 松野さんが文面 OK した後だけ

振り分けルール（flow.md §3、2026-11-05 松野さん／2026-11-10 改善）:
  - 実行中・定期実行の作業 → 振り直さず「現担当のまま」
  - ツールが決まっている仕事（FIXED）→「固定（理由）」
  - 磨き上げ・設計（design）→ チャッピー固定
  - お金まわり（money）→ ジャービスか Codex の余裕のある方
  - 実装・文書・点検・運用 → 週次％が低い順。90% 以上とクレジット切れは外す。
    まとめて出すときは 1 件ごとに仮の消費（+BATCH_STEP%）を足して、1 人に寄りすぎないようにする
  - Web ログインが要る → Mac launchd と注記／対外送信・お金 → 実行は松野さんの了承と注記
  - 手入力の％は取得日を出し、7 日より古ければ「古い値」
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

JST = ZoneInfo("Asia/Tokyo")
REPO = Path(__file__).resolve().parents[1]
OUT_DIR = REPO / ".jarvis_state" / "dispatch_suggestions"
USAGE_COPY = REPO / ".jarvis_state" / "ai_usage_weekly.json"

BLOCK_PCT = 90.0    # これ以上は候補から外す（Cursor の既存閾値と同じ）
WARN_PCT = 70.0
BATCH_STEP = 15.0   # まとめて出すとき、1 件割り振るごとに見込む仮の消費（％）
STALE_DAYS = 7


@dataclass(frozen=True)
class Agent:
    key: str
    name: str
    tool: str
    next_line: str


AGENTS = {
    "codex": Agent("codex", "Codex", "Codex", "人判断のみ（松野さんが Codex に指示する）"),
    "claude_code": Agent("claude_code", "ミスレモン", "Claude Code", "Claude Codeで続行"),
    "cursor": Agent("cursor", "ジャービス", "Cursor", "Jarvisに依頼"),
    "gencode": Agent("gencode", "フライデー", "GenCode", "人判断のみ（松野さんがフライデーに指示する）"),
    "chatgpt_mode": Agent("chatgpt_mode", "チャッピー", "ChatGPT モード", "人判断のみ（松野さんがチャッピーに指示する）"),
}
TIE_ORDER = ["codex", "claude_code", "cursor", "gencode"]
EXECUTOR_ALIASES = {  # TASK.md の executor 欄 → エージェント
    "codex": "codex", "claude": "claude_code", "miss lemon": "claude_code", "ミスレモン": "claude_code",
    "cursor": "cursor", "jarvis": "cursor", "ジャービス": "cursor", "gencode": "gencode",
    "friday": "gencode", "フライデー": "gencode", "chatgpt": "chatgpt_mode", "チャッピー": "chatgpt_mode",
}

# ツールが決まっている仕事（flow.md「元々ツールが決まっている仕事は例外」）
FIXED = {
    "314": ("claude_code", "週次レビューは Claude の定期タスクと決まっている"),
    "617": ("cursor", "送金・銀行 IB はジャービス専属"),
}

KIND_LABEL = {"design": "磨き上げ・設計", "implement": "実装", "doc": "文書", "review": "点検",
              "money": "お金まわり", "operation": "運用・定期"}

KIND_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("money", ("送金", "振込", "振り込み", "銀行", "IB", "OTP", "引き落とし", "入金", "支払")),
    ("design", ("フロー", "磨き", "設計", "思い描く", "指示書", "方針")),
    ("operation", ("定期", "週次", "毎日", "毎週", "巡回", "監視", "整理", "ウェイクワード",
                   "launchd", "相乗り", "後始末", "フォロー")),
    ("review", ("点検", "レビュー", "監査")),
    ("doc", ("ドキュメント", "文書", "README", "手順書", "記録の訂正")),
    ("implement", ("実装", "スクリプト", "コード", "テスト", "PR", "自動化", "修正")),
]
LOGIN_WORDS = ("ログイン", "Playwright", "ブラウザ", "Web 画面", "Web画面", "Cookie")
SEND_WORDS = ("返信", "送信", "メール送", "投稿", "対外", "案内文", "Chatwork", "LINE 送", "連絡する")
ACTIVE_STATUS = ("running", "review", "in_progress", "doing")
ROUTINE_WORDS = ("launchd", "定期", "GHA", "cron", "routine")


# ------------------------------------------------------------------ 入力
def _field(head: str, name: str) -> str:
    m = re.search(rf"^\|\s*{name}\s*\|\s*([^|]*)\|", head, re.M)
    return m.group(1).strip() if m else ""


def read_task(path: Path) -> dict[str, Any]:
    """TASK.md から題・依頼・実行者・状態・トリガーの手がかりを抜く。過去の完了記録は読まない。"""
    text = path.read_text(encoding="utf-8")
    head = text.split("\n## 以前の", 1)[0]
    title = ""
    m = re.search(r"^#\s+(.+)$", head, re.M)
    if m:
        title = re.sub(r"^TASK\s*[—\-–]\s*", "", m.group(1).strip())
    m = re.search(r"^##\s*依頼\s*\n+(.+?)(?:\n##\s|\Z)", head, re.M | re.S)
    request = m.group(1).strip() if m else ""
    if request.startswith("（何をするか"):
        request = ""
    m = re.search(r"^##\s*(?:トリガー|動き出す合図|合図)\s*\n+(.+?)(?:\n##\s|\Z)", head, re.M | re.S)
    trigger = m.group(1).strip() if m else ""
    agent_id = _field(head, "agent_id") or (re.match(r"(\d{3})", title).group(1) if re.match(r"\d{3}", title) else "")
    return {"title": title, "request": request, "task_id": _field(head, "task_id"),
            "agent_id": agent_id, "executor": _field(head, "executor"),
            "status": _field(head, "status"), "trigger": trigger, "path": str(path),
            "text": "\n".join([title, request, trigger])}


def classify(task: dict[str, Any]) -> str:
    text = task.get("text", "")
    if any(w in (task.get("executor", "") + task.get("trigger", "")) for w in ROUTINE_WORDS):
        return "operation"
    for kind, words in KIND_RULES:
        if any(w in text for w in words):
            return kind
    return "implement"


def needs_login(text: str) -> bool:
    return any(w in text for w in LOGIN_WORDS)


def sends_out(text: str) -> bool:
    return any(w in text for w in SEND_WORDS)


def executor_agent(executor: str) -> str | None:
    e = executor.lower()
    for k, v in EXECUTOR_ALIASES.items():
        if k in e:
            return v
    return None


def load_usage() -> dict[str, Any]:
    """その場で集計し直す（手入力の最新値を拾うため。書き込みはしない）。失敗したら週次の写し。"""
    try:
        sys.path.insert(0, str(REPO / "scripts"))
        import jarvis_ai_usage_weekly as u
        return u.build_report(7)
    except Exception:
        try:
            return json.loads(USAGE_COPY.read_text(encoding="utf-8")).get("latest") or {}
        except (OSError, json.JSONDecodeError):
            return {}


def _age(updated: Any, now: datetime) -> tuple[str, bool]:
    """('11/09 手入力', 古いか)"""
    try:
        dt = datetime.fromisoformat(str(updated).replace("Z", "+00:00").replace("+0900", "+09:00"))
    except ValueError:
        return ("取得日不明", True)
    dt = dt.astimezone(JST)
    return (f"{dt:%m/%d}", now - dt > timedelta(days=STALE_DAYS))


def usage_view(rep: dict[str, Any], now: datetime | None = None) -> dict[str, dict[str, Any]]:
    """エージェントごとの 週次％・出所・取得日。"""
    now = now or datetime.now(JST)
    t = rep.get("tools") or {}
    cx = t.get("codex") or {}
    weekly = ((cx.get("limits_latest") or {}).get("weekly") or {})

    def manual(entry: dict[str, Any], auto: bool = False) -> dict[str, Any]:
        day, stale = _age(entry.get("auto_fetched_at") if auto else entry.get("updated_at"), now)
        return {"pct": entry.get("pct"), "src": "自動" if auto else "手入力", "day": day,
                "stale": stale and entry.get("pct") is not None, "note": entry.get("note") or ""}

    cur = t.get("cursor") or {}
    return {
        "codex": {"pct": weekly.get("used_pct"), "src": "ログ", "day": "", "stale": False,
                  "note": f"週次リセット {str(weekly.get('resets_at') or '—')[5:16]}"},
        "claude_code": manual(t.get("claude_plan") or {}),
        "cursor": manual({**cur, "updated_at": cur.get("updated_at")}, auto=cur.get("fetch_source") == "auto"),
        "gencode": manual(t.get("gencode") or {}),
        "chatgpt_mode": manual(t.get("chatgpt_mode") or {}),
    }


# ------------------------------------------------------------------ 判断
def _pct_str(p: Any) -> str:
    return f"{p:.0f}%" if isinstance(p, (int, float)) else "不明"


def _pick(pool: list[str], usage: dict[str, dict[str, Any]], load: dict[str, float]) -> tuple[str | None, list[str]]:
    excluded, ok = [], []
    for k in pool:
        p = usage[k]["pct"]
        if isinstance(p, (int, float)) and p >= BLOCK_PCT:
            why = "クレジット切れ" if k == "gencode" and p >= 100 else f"{_pct_str(p)} で逼迫"
            excluded.append(f"{AGENTS[k].name}（{why}）")
        else:
            ok.append(k)

    def key(k: str) -> tuple[int, float, int]:
        p = usage[k]["pct"]
        known = isinstance(p, (int, float))
        return (0 if known else 1, (float(p) if known else 0.0) + load.get(k, 0.0), TIE_ORDER.index(k))

    ok.sort(key=key)
    return (ok[0] if ok else None), excluded


def decide(task: dict[str, Any], kind: str, usage: dict[str, dict[str, Any]],
           load: dict[str, float] | None = None) -> dict[str, Any]:
    load = load if load is not None else {}
    fixed = FIXED.get(task.get("agent_id", ""))
    if fixed:
        return {"agent": fixed[0], "mode": "fixed", "reason": f"固定（{fixed[1]}）", "excluded": []}

    cur = executor_agent(task.get("executor", ""))
    routine = any(w in task.get("executor", "") for w in ROUTINE_WORDS)
    if task.get("status", "") in ACTIVE_STATUS or routine:
        what = "定期実行" if routine else f"状態 {task.get('status')}"
        return {"agent": cur, "mode": "keep",
                "reason": f"現担当のまま（{what}・実行者 {task.get('executor') or '不明'}）。振り直さない",
                "excluded": []}

    if kind == "design":
        p = usage["chatgpt_mode"]["pct"]
        reason = "磨き上げ・設計はチャッピー固定の方針"
        if isinstance(p, (int, float)) and p >= BLOCK_PCT:
            reason += f"。ただしチャッピーが {_pct_str(p)} で逼迫"
        return {"agent": "chatgpt_mode", "mode": "rule", "reason": reason, "excluded": []}

    pool = ["cursor", "codex"] if kind == "money" else list(TIE_ORDER)
    best, excluded = _pick(pool, usage, load)
    if not best:
        return {"agent": None, "mode": "hold", "reason": "候補が全員逼迫。リセットを待つか松野さんの判断",
                "excluded": excluded}
    load[best] = load.get(best, 0.0) + BATCH_STEP
    base = "お金まわりはジャービスか Codex" if kind == "money" else f"{KIND_LABEL.get(kind, kind)}は使用量で振り分け"
    u = usage[best]
    reason = f"{base}。{AGENTS[best].name}が週次 {_pct_str(u['pct'])} で一番余裕"
    if isinstance(u["pct"], (int, float)) and u["pct"] >= WARN_PCT:
        reason += "（70% 超え。大きい作業は分ける）"
    return {"agent": best, "mode": "rule", "reason": reason, "excluded": excluded}


# ------------------------------------------------------------------ 文面
def usage_line(usage: dict[str, dict[str, Any]]) -> str:
    bits = []
    for k in TIE_ORDER + ["chatgpt_mode"]:
        u = usage[k]
        s = f"{AGENTS[k].name} {_pct_str(u['pct'])}"
        if u["src"] != "ログ" and u["pct"] is not None:
            s += f"（{u['day']} {u['src']}{'・古い値' if u['stale'] else ''}）"
        bits.append(s)
    return "・".join(bits)


def request_text(task: dict[str, Any], d: dict[str, Any]) -> str:
    """そのまま各ツールに貼る依頼文（1〜2 行）。"""
    where = task.get("path") or ""
    who = AGENTS[d["agent"]].name if d.get("agent") else "担当"
    if where:
        return f"{who}へ: {where} を読んで、完了条件まで進めて。終わったら検証結果を TASK.md に書き、#ai-hub に一言。"
    return f"{who}へ: 「{task.get('title')}」を進めて。渡し票（TASK.md）が無ければ先に作って。"


def item(task: dict[str, Any], kind_override: str | None, usage: dict[str, dict[str, Any]],
         load: dict[str, float]) -> dict[str, Any]:
    kind = kind_override or classify(task)
    d = decide(task, kind, usage, load)
    notes = []
    if needs_login(task.get("text", "")):
        notes.append("Web ログインが要るので実行は Mac の launchd")
    if kind == "money":
        notes.append("送金・OTP は割り振りだけ。実行は固定スクリプトと松野さんの最終承認")
    if sends_out(task.get("text", "")):
        notes.append("対外送信あり。送信は松野さんの了承")
    if d["mode"] == "keep" and d.get("agent") in usage:
        p = usage[d["agent"]]["pct"]
        if isinstance(p, (int, float)) and p >= BLOCK_PCT:
            notes.append(f"現担当の{AGENTS[d['agent']].name}は {_pct_str(p)} で逼迫中。止まったら振り直しを検討")
    empty = "request" in task and not task["request"] and d["mode"] == "rule"
    if empty:
        notes.append("渡し票の「依頼」が空。書いてから回す")
    return {"task": task, "kind": kind, "decision": d, "notes": notes, "empty": empty}


def render(items: list[dict[str, Any]], usage: dict[str, dict[str, Any]], period: str) -> str:
    lines = [f"【配車案】{len(items)}件（{period}の使用量で判定）", ""]
    asks: list[str] = []
    for i, it in enumerate(items, 1):
        t, d = it["task"], it["decision"]
        who = f"{AGENTS[d['agent']].name}" if d.get("agent") else "保留"
        lines.append(f"{i}. {t.get('title') or '（題なし）'} → {who}")
        lines.append(f"   {d['reason']}")
        if d["excluded"]:
            lines.append("   外した: " + "、".join(d["excluded"]))
        for n in it["notes"]:
            lines.append(f"   注意: {n}")
        if d["mode"] == "fixed":
            lines.append("   ✅ でも起動しない（定期で動く。臨時に動かすときは番号と担当を返信）")
        if d["mode"] == "rule" and d.get("agent") and not it["empty"]:
            asks.append(f"{i}. {request_text(t, d)}")
        lines.append("")
    lines.append(f"使用量: {usage_line(usage)}")
    lines.append("")
    if asks:
        lines.append("そのまま貼る依頼文（了承後、各ツールへ）:")
        lines.extend(asks)
        lines.append("")
    agents = {it["decision"]["agent"] for it in items
              if it["decision"]["mode"] == "rule" and it["decision"].get("agent") and not it["empty"]}
    if len(agents) == 1:
        nxt = AGENTS[agents.pop()].next_line
    else:
        nxt = "人判断のみ（番号で了承 → 各ツールへ依頼文を貼る）"
    lines.append(f"次: {nxt}")
    lines.append("")
    lines.append("担当メモ: 611 のルール判定（LLM なし）。係は指示しない。「1,3 OK」のように番号で返すと楽")
    lines.append("")
    lines.append("橋渡し: ✅ で全件、番号の返信で一部を了承。Codex・Claude Code・Cursor は自動で起動してドラフト PR で止める。チャッピー・フライデーは上の依頼文を貼る")
    return "\n".join(lines)


def build(tasks: list[dict[str, Any]], kind: str | None, rep: dict[str, Any],
          now: datetime | None = None) -> dict[str, Any]:
    usage = usage_view(rep, now)
    load: dict[str, float] = {}
    items = [item(t, kind, usage, load) for t in tasks]
    per = rep.get("period") or {}
    period = f"{str(per.get('since', ''))[5:10]}〜{str(per.get('until', ''))[5:10]}"
    return {"items": items, "text": render(items, usage, period)}


QUEUE_DIR = REPO / ".jarvis_state" / "dispatch_queue"


def queue_record(did: str, items: list[dict[str, Any]]) -> dict[str, Any]:
    """317 の ✅ 起動（jarvis_dispatch_launch.py）が読む形。"""
    rows = []
    for i, it in enumerate(items, 1):
        t, d = it["task"], it["decision"]
        rows.append({"no": i, "title": t.get("title"), "path": t.get("path"), "request": t.get("request", ""),
                     "kind": it["kind"], "agent": d.get("agent"), "mode": d["mode"], "notes": it["notes"],
                     "empty": it["empty"], "request_text": request_text(t, d)})
    return {"id": did, "created_at": datetime.now(JST).isoformat(), "items": rows}


def save_queue(did: str, items: list[dict[str, Any]]) -> Path:
    QUEUE_DIR.mkdir(parents=True, exist_ok=True)
    p = QUEUE_DIR / f"{did}.json"
    p.write_text(json.dumps(queue_record(did, items), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return p


def write_out(text: str, title: str) -> Path:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    slug = re.sub(r"[^\w一-龥ぁ-んァ-ン]+", "_", title)[:40].strip("_") or "task"
    p = OUT_DIR / f"{datetime.now(JST):%Y%m%d_%H%M}_{slug}.md"
    p.write_text(text + "\n", encoding="utf-8")
    return p


def main() -> int:
    ap = argparse.ArgumentParser(description="611 配車案（ルールのみ）")
    ap.add_argument("--task", nargs="*", default=[], help="社員フォルダの TASK.md（複数可）")
    ap.add_argument("--title", action="append", default=[], help="作業の題（TASK.md が無いとき。複数可）")
    ap.add_argument("--kind", choices=sorted(KIND_LABEL), help="種類を手で指定（全件に適用）")
    ap.add_argument("--post", action="store_true", help="#consult に投稿（文面を松野さんが OK した後だけ）")
    args = ap.parse_args()
    if not args.task and not args.title:
        ap.error("--task か --title が要る")
    tasks = [read_task(Path(p)) for p in args.task] + [{"title": t, "text": t} for t in args.title]
    res = build(tasks, args.kind, load_usage())
    did = datetime.now(JST).strftime("%Y%m%d-%H%M")
    text = res["text"] + f"\n\n配車ID: {did}（✅ で全件了承、または「1と3OK、2はCodexで」とスレッドに返信）"
    out = write_out(text, tasks[0].get("title") or "task")
    print(text)
    print(f"# 書き出し: {out}", file=sys.stderr)
    if args.post:
        save_queue(did, res["items"])
        r = subprocess.run([sys.executable, str(REPO / "scripts" / "jarvis_slack_webhook_post.py"),
                            "--channel", "consult", "--username", "611 配車係", "--text", text])
        return r.returncode
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
