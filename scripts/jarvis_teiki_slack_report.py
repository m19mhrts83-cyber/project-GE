#!/usr/bin/env python3
"""Vポイント・テイチャン係（614）— Slack #report へ短報。

テイチャン定例（launchd／朝取りこぼし）の結果を、ダッシュボードだけでなく
Slack でも「自動で動いた」と把握できるようにする。

  python scripts/jarvis_teiki_slack_report.py --from-state --dry-run
  python scripts/jarvis_teiki_slack_report.py --outcome drew --tickets 2 --note '抽選したよ'
  python scripts/jarvis_teiki_slack_report.py --outcome skipped --reason '間隔内'

投稿: jarvis_slack_webhook_post.py（#report）
無効化: JARVIS_TEIKI_SLACK_REPORT_DISABLE=1
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

REPO = Path(__file__).resolve().parents[1]
POST = REPO / "scripts" / "jarvis_slack_webhook_post.py"
STATE_PATH = REPO / ".jarvis_state" / "teiki_barai_chance.json"
REPORTS_DIR = (
    REPO
    / "docs"
    / "AIエージェントチーム"
    / "600_リソース・家計室"
    / "614_Vポイント・テイチャン係"
    / "reports"
)
JST = ZoneInfo("Asia/Tokyo")
AGENT_ID = "614"
AGENT_NAME = "Vポイント・テイチャン係"
DASH = "https://jarvis-dashboard-amber.vercel.app/vpoint#teiki-barai"


def _load_state() -> dict:
    if not STATE_PATH.is_file():
        return {}
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _archive(text: str, tag: str) -> None:
    try:
        REPORTS_DIR.mkdir(parents=True, exist_ok=True)
        day = datetime.now(JST).strftime("%Y-%m-%d")
        path = REPORTS_DIR / f"{day}_{tag}.md"
        path.write_text(
            f"# Slack #report 控え — {day} / {tag}\n\n```\n{text}\n```\n",
            encoding="utf-8",
        )
        print(f"📎 report archive: {path.relative_to(REPO)}")
    except OSError as e:
        print(f"⚠️ report archive failed: {e}", file=sys.stderr)


def build_text(
    *,
    outcome: str,
    tickets: int | None,
    w_chance: int | None,
    enrolled: str | None,
    drew_summary: str,
    reason: str,
    error: str,
    note: str,
) -> str:
    lines = [f"【{AGENT_ID} {AGENT_NAME}】"]
    out = (outcome or "checked").strip()

    if out == "skipped":
        lines.append(f"・結果: スキップ（{reason or '間隔内'}）")
    elif out == "disabled":
        lines.append("・結果: 無効化のため未実行")
    elif out == "failed":
        lines.append(f"・結果: 失敗 — {error or '不明'}")
        lines.append("・次: Vpass／Chrome／ログ（~/Library/Logs/jarvis_teiki）を確認 or #ops")
    elif out == "drew":
        lines.append(f"・結果: 抽選したよ — {drew_summary or '完了'}")
    else:
        lines.append("・結果: 確認のみ（抽選なし）")

    bits: list[str] = []
    if enrolled:
        bits.append(f"規約={enrolled}")
    if tickets is not None:
        bits.append(f"券={tickets}枚")
    if w_chance is not None:
        bits.append(f"W={w_chance}枚")
    if bits:
        lines.append(f"・状態: {' · '.join(bits)}")
    if note:
        lines.append(f"・特記: {note}")
    lines.append(f"・見る: {DASH}")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--outcome",
        default="checked",
        choices=("checked", "drew", "skipped", "failed", "disabled"),
    )
    ap.add_argument("--from-state", action="store_true", help="state JSON から券数等を補完")
    ap.add_argument("--tickets", type=int, default=None)
    ap.add_argument("--w-chance", type=int, default=None)
    ap.add_argument("--enrolled", default="")
    ap.add_argument("--drew-summary", default="")
    ap.add_argument("--reason", default="")
    ap.add_argument("--error", default="")
    ap.add_argument("--note", default="")
    ap.add_argument("--channel", default="report", choices=("report", "ops", "consult"))
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force", action="store_true", help="無効化 env を無視")
    args = ap.parse_args()

    if not args.force and (os.environ.get("JARVIS_TEIKI_SLACK_REPORT_DISABLE") or "").strip() in (
        "1",
        "true",
        "yes",
    ):
        print("⏭ JARVIS_TEIKI_SLACK_REPORT_DISABLE=1 — Slack 投稿スキップ")
        return 0

    st = _load_state() if args.from_state else {}
    tickets = args.tickets if args.tickets is not None else st.get("ticket_count")
    w_chance = args.w_chance if args.w_chance is not None else st.get("w_chance_tickets")
    enrolled = (args.enrolled or st.get("enrolled") or "") or None
    if isinstance(tickets, str) and tickets.isdigit():
        tickets = int(tickets)
    if isinstance(w_chance, str) and w_chance.isdigit():
        w_chance = int(w_chance)

    # 失敗は ops 寄せ（フォールバックで report でも可）
    channel = args.channel
    if args.outcome == "failed" and args.channel == "report":
        channel = "ops"

    text = build_text(
        outcome=args.outcome,
        tickets=tickets if isinstance(tickets, int) else None,
        w_chance=w_chance if isinstance(w_chance, int) else None,
        enrolled=str(enrolled) if enrolled else None,
        drew_summary=args.drew_summary,
        reason=args.reason,
        error=args.error,
        note=args.note,
    )

    if args.dry_run:
        print("--- dry-run ---")
        print(text)
        print("---")
        _archive(text, args.outcome)
        return 0

    if not POST.is_file():
        print(f"❌ missing {POST}", file=sys.stderr)
        return 2

    proc = subprocess.run(
        [sys.executable, str(POST), "--channel", channel, "--text", text],
        cwd=str(REPO),
        check=False,
    )
    if int(proc.returncode) == 0:
        _archive(text, args.outcome)
    return int(proc.returncode)


if __name__ == "__main__":
    raise SystemExit(main())
