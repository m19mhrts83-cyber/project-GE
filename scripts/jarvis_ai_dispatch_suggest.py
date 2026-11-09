#!/usr/bin/env python3
"""611 配車案（動きB）— 作業ごとに「このエージェントで」の割り振り案を作る（ルールのみ・LLM なし）。

入力: 作業（社員フォルダの TASK.md、または --title/--kind の手入力）＋ 使用量（611 の週次集計）
入力の使用量はその場で集計し直す（書き込みなし）。
出力: #consult 向けの文面。既定はファイルに書くだけ（dry-run）。--post を付けたときだけ Webhook 投稿。

  python3 scripts/jarvis_ai_dispatch_suggest.py --task docs/AIエージェントチーム/.../TASK.md
  python3 scripts/jarvis_ai_dispatch_suggest.py --title "814 点検を画面別判定に" --kind implement
  python3 scripts/jarvis_ai_dispatch_suggest.py --task ... --post   # 松野さんが文面 OK した後だけ

振り分けルール（flow.md §3 配車の基本方針、2026-11-05 松野さん）:
  - 磨き上げ・設計（design）   → チャッピー（ChatGPT モード）固定
  - お金まわり（money）        → ジャービス（Cursor）か Codex の余裕のある方。ミスレモンは対象外
  - 実装・文書・点検（implement/doc/review）→ Codex・ミスレモン・ジャービス・フライデーのうち、
    週次％が低い順。90% 以上と GenCode のクレジット切れ（100%）は候補から外す
  - Web ログインが要る作業 → 実行は Mac の launchd（クラウド実行はログイン状態を持てない）と注記
送金・OTP・本番変更・対外送信は割り振りだけで、実行の許可は別（松野さん）。
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

JST = ZoneInfo("Asia/Tokyo")
REPO = Path(__file__).resolve().parents[1]
OUT_DIR = REPO / ".jarvis_state" / "dispatch_suggestions"
USAGE_COPY = REPO / ".jarvis_state" / "ai_usage_weekly.json"

BLOCK_PCT = 90.0   # これ以上は候補から外す（Cursor の既存閾値と同じ）
WARN_PCT = 70.0


@dataclass(frozen=True)
class Agent:
    key: str          # ai_usage_weekly の tools キー
    name: str         # 呼び名
    tool: str         # ツール名
    next_line: str    # #consult 末尾「次:」に書く文言


AGENTS = {
    "codex": Agent("codex", "Codex", "Codex", "人判断のみ（松野さんが Codex に指示する）"),
    "claude_code": Agent("claude_code", "ミスレモン", "Claude Code", "Claude Codeで続行"),
    "cursor": Agent("cursor", "ジャービス", "Cursor", "Jarvisに依頼"),
    "gencode": Agent("gencode", "フライデー", "GenCode", "人判断のみ（松野さんがフライデーに指示する）"),
    "chatgpt_mode": Agent("chatgpt_mode", "チャッピー", "ChatGPT モード", "人判断のみ（松野さんがチャッピーに指示する）"),
}
# 同じ余裕なら、この順（現状の運用: 実装は Codex 寄り → Claude も受ける）
TIE_ORDER = ["codex", "claude_code", "cursor", "gencode"]

KIND_LABEL = {"design": "磨き上げ・設計", "implement": "実装", "doc": "文書", "review": "点検",
              "money": "お金まわり"}

# 作業の種類を決めるキーワード（上から順に判定）
KIND_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("money", ("送金", "振込", "振り込み", "銀行", "IB", "OTP", "引き落とし", "入金", "支払")),
    ("design", ("フロー", "磨き", "設計", "思い描く", "指示書", "方針", "作業フロー")),
    ("review", ("点検", "レビュー", "監査", "確認係")),
    ("doc", ("ドキュメント", "文書", "README", "手順書", "記録の訂正")),
    ("implement", ("実装", "スクリプト", "コード", "テスト", "PR", "自動化", "修正")),
]
LOGIN_WORDS = ("ログイン", "Playwright", "ブラウザ", "Web 画面", "Web画面", "Cookie")


# ------------------------------------------------------------------ 入力
def read_task(path: Path) -> dict[str, Any]:
    """TASK.md から題・依頼・種類の手がかりを抜く。本文の他の部分は使わない。"""
    text = path.read_text(encoding="utf-8")
    head = text.split("\n## 以前の", 1)[0]  # 過去の完了記録は読まない
    title = ""
    m = re.search(r"^#\s+(.+)$", head, re.M)
    if m:
        title = re.sub(r"^TASK\s*[—\-–]\s*", "", m.group(1).strip())
    m = re.search(r"^##\s*依頼\s*\n+(.+?)(?:\n##\s|\Z)", head, re.M | re.S)
    request = m.group(1).strip() if m else ""
    m = re.search(r"^\|\s*task_id\s*\|\s*([^|]+)\|", head, re.M)
    task_id = m.group(1).strip() if m else ""
    if request.startswith("（何をするか"):
        request = ""  # テンプレートのまま
    return {"title": title, "request": request, "task_id": task_id, "path": str(path),
            "text": title + "\n" + request}


def classify(text: str) -> str:
    for kind, words in KIND_RULES:
        if any(w in text for w in words):
            return kind
    return "implement"


def needs_login(text: str) -> bool:
    return any(w in text for w in LOGIN_WORDS)


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


def usage_view(rep: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """エージェントごとの 週次％ とメモ。"""
    t = rep.get("tools") or {}
    cx = t.get("codex") or {}
    weekly = ((cx.get("limits_latest") or {}).get("weekly") or {})
    gen = t.get("gencode") or {}
    return {
        "codex": {"pct": weekly.get("used_pct"), "note": f"週次リセット {str(weekly.get('resets_at') or '—')[:16]}"},
        "claude_code": {"pct": (t.get("claude_plan") or {}).get("pct"),
                        "note": f"枠到達 {len((t.get('claude_code') or {}).get('limit_hits') or [])} 回/7日"},
        "cursor": {"pct": (t.get("cursor") or {}).get("pct"), "note": ""},
        "gencode": {"pct": gen.get("pct"), "note": gen.get("note") or ""},
        "chatgpt_mode": {"pct": (t.get("chatgpt_mode") or {}).get("pct"), "note": ""},
    }


# ------------------------------------------------------------------ 判断
def _pct_str(p: Any) -> str:
    return f"{p:.0f}%" if isinstance(p, (int, float)) else "不明"


def decide(kind: str, usage: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """割り振り先・理由・外した候補を返す。"""
    if kind == "design":
        p = usage["chatgpt_mode"]["pct"]
        reason = "磨き上げ・設計はチャッピー（ChatGPT モード）固定の方針"
        if isinstance(p, (int, float)) and p >= BLOCK_PCT:
            reason += f"。ただしチャッピーの使用量が {_pct_str(p)} で逼迫"
        return {"agent": "chatgpt_mode", "reason": reason, "excluded": []}

    pool = ["cursor", "codex"] if kind == "money" else list(TIE_ORDER)
    excluded: list[str] = []
    ok: list[str] = []
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
        return (0 if known else 1, float(p) if known else 0.0, TIE_ORDER.index(k))

    if not ok:
        return {"agent": None, "reason": "候補が全員逼迫。リセットを待つか松野さんの判断", "excluded": excluded}
    ok.sort(key=key)
    best = ok[0]
    base = "お金まわりはジャービスか Codex" if kind == "money" else f"{KIND_LABEL.get(kind, kind)}は使用量で振り分け"
    reason = f"{base}。{AGENTS[best].name}が週次 {_pct_str(usage[best]['pct'])} で一番余裕"
    if isinstance(usage[best]["pct"], (int, float)) and usage[best]["pct"] >= WARN_PCT:
        reason += "（ただし 70% 超え。大きい作業は分ける）"
    return {"agent": best, "reason": reason, "excluded": excluded}


# ------------------------------------------------------------------ 文面
def render(task: dict[str, Any], kind: str, login: bool, d: dict[str, Any],
           usage: dict[str, dict[str, Any]], period: str) -> str:
    title = task.get("title") or "（題なし）"
    agent = AGENTS[d["agent"]] if d["agent"] else None
    lines = [f"【配車案】{title}"]
    lines.append(f"割り振り: {agent.name}（{agent.tool}）" if agent else "割り振り: 保留（候補なし）")
    lines.append(f"理由: {d['reason']}")
    if d["excluded"]:
        lines.append("外した候補: " + "、".join(d["excluded"]))
    usage_bits = [f"{AGENTS[k].name} {_pct_str(usage[k]['pct'])}" for k in TIE_ORDER + ["chatgpt_mode"]]
    lines.append(f"使用量（{period}）: " + "・".join(usage_bits))
    if login:
        lines.append("実行場所: Web ログインが要るため Mac の launchd（クラウド実行は不可）")
    if kind == "money":
        lines.append("注意: 送金・OTP は割り振りだけ。実行は金額上限・送金先リスト付きの固定スクリプトと松野さんの最終承認")
    if task.get("path"):
        lines.append(f"渡し票: {task['path']}")
    if d.get("empty_request"):
        lines.append("注意: 渡し票の「依頼」が空（テンプレートのまま）。中身を書いてから回す")
    lines.append("")
    nxt = agent.next_line if agent and not d.get("empty_request") else "人判断のみ（渡し票を書いてから）" if agent else "人判断のみ"
    lines.append(f"次: {nxt}")
    lines.append("")
    lines.append("担当メモ: 611 のルール判定（LLM なし）。係は指示しない。指示は松野さんから")
    lines.append("")
    lines.append(f"橋渡し: 松野さんが了承したら、{agent.name if agent else '担当'}に渡し票を渡して一声")
    return "\n".join(lines)


def build(task: dict[str, Any], kind: str | None, rep: dict[str, Any]) -> dict[str, Any]:
    k = kind or classify(task.get("text", ""))
    login = needs_login(task.get("text", ""))
    usage = usage_view(rep)
    d = decide(k, usage)
    if "request" in task and not task["request"]:
        d = {**d, "empty_request": True}
    per = rep.get("period") or {}
    period = f"{str(per.get('since', ''))[5:10]}〜{str(per.get('until', ''))[5:10]}"
    return {"kind": k, "login": login, "decision": d,
            "text": render(task, k, login, d, usage, period)}


def write_out(text: str, title: str) -> Path:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    slug = re.sub(r"[^\w一-龥ぁ-んァ-ン]+", "_", title)[:40].strip("_") or "task"
    p = OUT_DIR / f"{datetime.now(JST):%Y%m%d_%H%M}_{slug}.md"
    p.write_text(text + "\n", encoding="utf-8")
    return p


def main() -> int:
    ap = argparse.ArgumentParser(description="611 配車案（ルールのみ）")
    ap.add_argument("--task", help="社員フォルダの TASK.md")
    ap.add_argument("--title", help="作業の題（TASK.md が無いとき）")
    ap.add_argument("--kind", choices=sorted(KIND_LABEL), help="種類を手で指定（自動判定を上書き）")
    ap.add_argument("--post", action="store_true", help="#consult に投稿（文面を松野さんが OK した後だけ）")
    args = ap.parse_args()
    if not args.task and not args.title:
        ap.error("--task か --title が要る")
    task = read_task(Path(args.task)) if args.task else {"title": args.title, "text": args.title}
    if args.task and args.title:
        task["title"] = args.title
    res = build(task, args.kind, load_usage())
    out = write_out(res["text"], task.get("title") or "task")
    print(res["text"])
    print(f"# 書き出し: {out}", file=sys.stderr)
    if args.post:
        r = subprocess.run([sys.executable, str(REPO / "scripts" / "jarvis_slack_webhook_post.py"),
                            "--channel", "consult", "--username", "611 配車係", "--text", res["text"]])
        return r.returncode
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
