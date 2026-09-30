#!/usr/bin/env python3
"""config/grok_*_grok_paste.md の ``` ブロックを B1_Instructions_全文.txt に抽出。

ネスト ``` がある paste は手動または専用 .txt 正本を使う（不動産部長等）。

  cd ~/git-repos
  ~/selenium_env/venv/bin/python scripts/jarvis_grok_paste_to_b1_txt.py \\
    config/grok_shift_ai_advisor_grok_paste.md -o /path/B1_シフトAI_Instructions_全文.txt
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


def extract_fence(text: str) -> str:
    dash = text.find("\n---\n")
    if dash >= 0:
        text = text[dash + 5 :]
    m = re.search(r"```\n([\s\S]*?)\n```\s*$", text.strip())
    if m:
        return m.group(1).rstrip() + "\n"
    parts = text.split("```")
    if len(parts) >= 3:
        body = parts[1]
        if body.startswith("\n"):
            body = body[1:]
        return body.rstrip() + "\n"
    raise ValueError("instructions fence not found")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("paste_md", type=Path)
    ap.add_argument("-o", "--output", type=Path, required=False)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    body = extract_fence(args.paste_md.read_text(encoding="utf-8"))
    if args.dry_run:
        print(body[:500])
        print(f"... ({len(body.splitlines())} lines total)")
        return 0
    if not args.output:
        ap.error("-o/--output is required unless --dry-run")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(body, encoding="utf-8")
    print(f"wrote {args.output} ({len(body.splitlines())} lines)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
