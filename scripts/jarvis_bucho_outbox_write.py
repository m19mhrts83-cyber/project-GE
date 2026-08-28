#!/usr/bin/env python3
"""Jarvis → Grok: Jarvisボックスへ定型 MD を書く（--target で振り分け先）。

  cd ~/git-repos
  ~/selenium_env/venv/bin/python scripts/jarvis_bucho_outbox_write.py \\
    --title 'S9事前確認2社' --action s9_precheck --priority high --target re \\
    --body '北区1・緑区1で --next 2 --balanced。候補をチャンネルへ。'

  ~/selenium_env/venv/bin/python scripts/jarvis_bucho_outbox_write.py \\
    --title '朝の天気材料' --action weather_brief --target weather --body '…'
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent))
from jarvis_bucho_bridge_lib import (  # noqa: E402
    list_target_ids,
    outbox_dir_for_target,
    sanitize_title,
)

JST = ZoneInfo("Asia/Tokyo")
ACTIONS = (
    "s9_precheck",
    "s2_batch",
    "s1",
    "memo",
    "ask",
    "weather_brief",
    "other",
)


def now_stamp() -> tuple[str, str]:
    dt = datetime.now(JST)
    return dt.strftime("%Y-%m-%d"), dt.strftime("%H%M")


def build_md(*, title: str, body: str, action: str, priority: str, target: str) -> str:
    body = (body or "").strip() or "(本文なし)"
    return (
        f"# Jarvis → Grok\n"
        f"target: {target}\n"
        f"priority: {priority}\n"
        f"action: {action}\n"
        f"title: {title}\n"
        f"---\n"
        f"{body}\n"
    )


def main() -> int:
    targets = list_target_ids()
    ap = argparse.ArgumentParser(description="Write MD to Jarvisボックス (outbox / team folder)")
    ap.add_argument("--title", required=True, help="題名（ファイル名にも使用）")
    ap.add_argument("--body", default="", help="本文")
    ap.add_argument("--stdin", action="store_true", help="本文を stdin から読む")
    ap.add_argument(
        "--action",
        default="memo",
        choices=ACTIONS,
        help="action タグ（Grok ルーティンが解釈）",
    )
    ap.add_argument(
        "--priority",
        default="normal",
        choices=("normal", "high"),
        help="優先度",
    )
    ap.add_argument(
        "--target",
        default="hawk",
        choices=targets if targets else None,
        help=f"振り分け先（既定 hawk=ホーク参謀）。choices: {', '.join(targets)}",
    )
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="書かずにパスと本文だけ表示",
    )
    args = ap.parse_args()

    body = args.body
    if args.stdin:
        body = sys.stdin.read()

    day, hm = now_stamp()
    safe = sanitize_title(args.title)
    name = f"{day}_{hm}_{safe}.md"
    out_dir = outbox_dir_for_target(args.target)
    path = out_dir / name
    text = build_md(
        title=args.title.strip(),
        body=body,
        action=args.action,
        priority=args.priority,
        target=args.target,
    )

    if args.dry_run:
        print(f"# dry-run target={args.target} → {path}")
        print(text)
        return 0

    path.write_text(text, encoding="utf-8")
    print(f"📎 Jarvisボックス書込 target={args.target}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
