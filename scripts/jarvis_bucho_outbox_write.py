#!/usr/bin/env python3
"""Jarvis → 部長: Jarvisボックス（20_outbox_to_grok）へ定型 MD を書く。

  cd ~/git-repos
  ~/selenium_env/venv/bin/python scripts/jarvis_bucho_outbox_write.py \\
    --title 'S9事前確認2社' --action s9_precheck --priority high \\
    --body '北区1・緑区1で --next 2 --balanced。候補をチャンネルへ。'

  echo '本文' | ~/selenium_env/venv/bin/python scripts/jarvis_bucho_outbox_write.py \\
    --title 'メモ' --action memo --stdin
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent))
from jarvis_bucho_bridge_lib import folder, sanitize_title  # noqa: E402

JST = ZoneInfo("Asia/Tokyo")
ACTIONS = (
    "s9_precheck",
    "s2_batch",
    "s1",
    "memo",
    "ask",
    "other",
)


def now_stamp() -> tuple[str, str]:
    dt = datetime.now(JST)
    return dt.strftime("%Y-%m-%d"), dt.strftime("%H%M")


def build_md(*, title: str, body: str, action: str, priority: str) -> str:
    body = (body or "").strip() or "(本文なし)"
    return (
        f"# Jarvis → 部長\n"
        f"priority: {priority}\n"
        f"action: {action}\n"
        f"title: {title}\n"
        f"---\n"
        f"{body}\n"
    )


def main() -> int:
    ap = argparse.ArgumentParser(description="Write MD to Jarvisボックス (outbox)")
    ap.add_argument("--title", required=True, help="題名（ファイル名にも使用）")
    ap.add_argument("--body", default="", help="本文")
    ap.add_argument("--stdin", action="store_true", help="本文を stdin から読む")
    ap.add_argument(
        "--action",
        default="memo",
        choices=ACTIONS,
        help="action タグ（部長ルーティンが解釈）",
    )
    ap.add_argument(
        "--priority",
        default="normal",
        choices=("normal", "high"),
        help="優先度",
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
    out_dir = folder("outbox_to_grok")
    path = out_dir / name
    text = build_md(
        title=args.title.strip(),
        body=body,
        action=args.action,
        priority=args.priority,
    )

    if args.dry_run:
        print(f"# dry-run → {path}")
        print(text)
        return 0

    path.write_text(text, encoding="utf-8")
    print(f"📎 Jarvisボックス書込: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
