#!/usr/bin/env python3
"""
Web ダッシュボードから送信済み（status=sent）で、
OneDrive `5.やり取り.md` 未追記の triage_items を追記する。

  cd ~/git-repos
  python scripts/jarvis_triage_yoritoori_catchup.py
  python scripts/jarvis_triage_yoritoori_catchup.py --dry-run

夜間トリアージ後・朝オープン前後に呼ぶ想定。
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))

from jarvis_night_triage import partner_base  # noqa: E402

YORITOORI = "5.やり取り.md"


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def append_sent_block(
    md_path: Path,
    *,
    partner_name: str,
    subject: str,
    body: str,
) -> bool:
    if not md_path.is_file():
        print(f"# missing {md_path}", file=sys.stderr)
        return False
    date_str = datetime.now().strftime("%Y/%m/%d %H:%M")
    summary = (subject or "").strip() or (body.strip().splitlines()[0][:40] if body.strip() else "送信")
    subject_block = f"**件名**: {subject}\n" if subject else ""
    block = f"""

### {date_str}｜{partner_name}｜自分から送信｜{summary}

{subject_block}{body}

---
"""
    content = md_path.read_text(encoding="utf-8")
    marker = "## やり取り（時系列）"
    if marker in content:
        after_marker = content[content.find(marker) :]
        m = re.search(r"\n\n### [12]\d{3}/\d{2}/\d{2}", after_marker)
        if m:
            pos = content.find(marker) + m.start() + 2
            content = content[:pos] + block.strip() + "\n\n" + content[pos:]
        else:
            pos = content.find(marker) + len(marker)
            content = (
                content[:pos].rstrip()
                + "\n\n"
                + block.strip()
                + "\n\n"
                + content[pos:].lstrip()
            )
    else:
        content += block
    md_path.write_text(content, encoding="utf-8")
    return True


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Append Web-sent triage to yoritoori MD")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--limit", type=int, default=40)
    args = ap.parse_args(argv)

    url = (os.environ.get("JARVIS_SUPABASE_URL") or "").strip()
    key = (os.environ.get("JARVIS_SUPABASE_SERVICE_ROLE_KEY") or "").strip()
    if not url or not key:
        print("# JARVIS_SUPABASE_* 未設定", file=sys.stderr)
        return 1

    from supabase import create_client

    sb = create_client(url, key)
    r = (
        sb.table("triage_items")
        .select("*")
        .eq("status", "sent")
        .neq("kind", "activity")
        .order("updated_at", desc=True)
        .limit(args.limit)
        .execute()
    )
    rows = r.data or []
    base = partner_base()
    done = 0
    skipped = 0
    for it in rows:
        payload = it.get("payload") if isinstance(it.get("payload"), dict) else {}
        if payload.get("yoritoori_appended"):
            skipped += 1
            continue
        folder = (it.get("folder") or "").strip()
        if not folder:
            print(f"# skip no folder id={it.get('id')}", file=sys.stderr)
            continue
        md = base / folder / YORITOORI
        partner = (it.get("partner") or folder).strip()
        subject = (it.get("subject") or "").strip()
        if subject and not subject.lower().startswith("re:"):
            subject = f"Re: {subject}"
        body = (it.get("draft_text") or "").strip()
        if not body:
            print(f"# skip empty draft id={it.get('id')}", file=sys.stderr)
            continue
        print(f"# append {folder} id={it.get('id')} -> {md}")
        if args.dry_run:
            done += 1
            continue
        if not append_sent_block(md, partner_name=partner, subject=subject, body=body):
            continue
        payload = dict(payload)
        payload["yoritoori_appended"] = True
        payload["yoritoori_appended_at"] = now_iso()
        sb.table("triage_items").update(
            {"payload": payload, "updated_at": now_iso()}
        ).eq("id", it["id"]).execute()
        done += 1

    print(f"# catchup appended={done} already={skipped} scanned={len(rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
