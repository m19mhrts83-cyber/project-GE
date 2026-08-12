#!/usr/bin/env python3
"""神大家運営回答のやり取りから、買い進め／LP 関連を kurashift_ops_consult_events へ。

  cd ~/git-repos && set -a && source .env.jarvis_private && set +a
  ~/selenium_env/venv/bin/python scripts/jarvis_kurashift_ops_consult_ingest.py
  ~/selenium_env/venv/bin/python scripts/jarvis_kurashift_ops_consult_ingest.py --dry-run
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

YORITOORI = Path(
    "/Users/matsunomasaharu2/Library/CloudStorage/OneDrive-個人用/"
    "215_神・大家さん倶楽部/C2_ルーティン作業/26_パートナー社への相談/"
    "809_神大家運営回答/5.やり取り.md"
)
PARTNER = "809_神大家運営回答"
KEYWORDS = (
    "買い進め",
    "プランニング",
    "ライフプラン",
    "CF",
    "キャッシュフロー",
    "年次",
    "夢を叶える",
    "STEP3",
    "木村",
    "融資枠",
    "物件購入",
)


def sb_client() -> Any:
    url = os.environ.get("JARVIS_SUPABASE_URL")
    key = os.environ.get("JARVIS_SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        raise SystemExit("JARVIS_SUPABASE_URL / JARVIS_SUPABASE_SERVICE_ROLE_KEY が必要です")
    from supabase import create_client

    return create_client(url, key)


HEADING_RE = re.compile(
    r"^#{2,3}\s+(\d{4}[/-]\d{1,2}[/-]\d{1,2}).*?$",
    re.M,
)


def parse_events(text: str) -> list[dict[str, Any]]:
    # Split by ### or ## date headings common in yoritoori
    parts = re.split(r"(?=^#{2,4}\s+)", text, flags=re.M)
    out: list[dict[str, Any]] = []
    for part in parts:
        if not part.strip():
            continue
        first = part.splitlines()[0] if part.splitlines() else ""
        dm = re.search(r"(\d{4})[/-](\d{1,2})[/-](\d{1,2})", first)
        if not dm:
            continue
        y, m, d = int(dm.group(1)), int(dm.group(2)), int(dm.group(3))
        body = part[:1200]
        tags = [k for k in KEYWORDS if k in body]
        if not tags:
            continue
        # subject = first non-empty line after heading or heading itself
        lines = [ln.strip() for ln in part.splitlines() if ln.strip()]
        subject = lines[1][:120] if len(lines) > 1 else lines[0][:120]
        snippet = "\n".join(lines[1:8])[:400]
        out.append(
            {
                "occurred_at": datetime(y, m, d, 12, 0, tzinfo=timezone.utc).isoformat(),
                "channel": "yoritoori",
                "partner_folder": PARTNER,
                "subject": subject,
                "snippet": snippet,
                "tags": tags,
                "source_ref": f"{PARTNER}/5.やり取り.md#{y:04d}-{m:02d}-{d:02d}",
                "metadata": {"heading": first[:200]},
            }
        )
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    if not YORITOORI.is_file():
        raise SystemExit(f"missing {YORITOORI}")
    text = YORITOORI.read_text(encoding="utf-8", errors="replace")
    events = parse_events(text)
    print(f"# matched events: {len(events)}")
    for e in events[:8]:
        print(f"  - {e['occurred_at'][:10]} tags={e['tags']} {e['subject'][:60]}")
    if args.dry_run:
        return 0
    sb = sb_client()
    # Idempotent-ish: delete prior yoritoori imports for this partner then insert
    sb.table("kurashift_ops_consult_events").delete().eq("channel", "yoritoori").eq(
        "partner_folder", PARTNER
    ).execute()
    for i in range(0, len(events), 100):
        sb.table("kurashift_ops_consult_events").insert(events[i : i + 100]).execute()
    print(f"📎 ops_consult_ingest: inserted={len(events)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
