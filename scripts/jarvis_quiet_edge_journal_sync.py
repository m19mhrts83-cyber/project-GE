#!/usr/bin/env python3
"""Quiet Edge: Obsidian ★Journal → vital_journal_daily 同期.

Vercel はローカル Disk を見ないため、Mac で抜粋を Supabase に投影する。
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import yaml

try:
    from supabase import create_client
except ImportError:
    print("need supabase-py", file=sys.stderr)
    sys.exit(1)

ROOT = Path(__file__).resolve().parents[1]
YAML_PATH = ROOT / "config" / "dashboard_lanes.yaml"
ENV_PATH = ROOT / ".env.jarvis_private"
DATE_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})\.md$")


def load_env() -> None:
    if not ENV_PATH.exists():
        return
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def journal_dir() -> Path:
    reg = yaml.safe_load(YAML_PATH.read_text(encoding="utf-8")) or {}
    raw = (
        os.environ.get("JARVIS_LANES_OBSIDIAN_JOURNAL")
        or os.environ.get("QUIET_EDGE_JOURNAL_DIR")
        or reg.get("obsidian_journal")
        or ""
    )
    return Path(str(raw)).expanduser()


def excerpt_text(text: str, max_chars: int = 1200) -> str:
    body: list[str] = []
    for line in text.splitlines():
        s = line.strip()
        if not s:
            continue
        if s.startswith("#"):
            continue
        body.append(s)
        joined = "\n".join(body)
        if len(joined) >= max_chars:
            return joined[:max_chars]
    return "\n".join(body)[:max_chars]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=60)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    load_env()
    jdir = journal_dir()
    if not jdir.is_dir():
        print(f"journal dir missing: {jdir}", file=sys.stderr)
        return 2

    url = (os.environ.get("JARVIS_SUPABASE_URL") or "").strip()
    key = (
        os.environ.get("JARVIS_SUPABASE_SERVICE_ROLE_KEY")
        or os.environ.get("JARVIS_SUPABASE_SECRET_KEY")
        or ""
    ).strip()
    if not url or not key:
        print("JARVIS_SUPABASE_* missing", file=sys.stderr)
        return 2

    since = date.today() - timedelta(days=max(1, args.days) - 1)
    rows: list[dict] = []
    for f in sorted(jdir.glob("????-??-??.md")):
        m = DATE_RE.match(f.name)
        if not m:
            continue
        d = date.fromisoformat(m.group(1))
        if d < since:
            continue
        raw = f.read_text(encoding="utf-8", errors="ignore")
        ex = excerpt_text(raw)
        rows.append(
            {
                "recorded_at": m.group(1),
                "excerpt": ex,
                "char_count": len(raw),
                "source": "obsidian_star_journal",
                "payload": {"filename": f.name},
                "updated_at": datetime.utcnow().isoformat() + "Z",
            }
        )

    print(f"dir={jdir} files={len(rows)} since={since.isoformat()}")
    if args.dry_run:
        for r in rows[-3:]:
            print(r["recorded_at"], r["char_count"], r["excerpt"][:80].replace("\n", " "))
        return 0

    sb = create_client(url, key)
    batch = 40
    for i in range(0, len(rows), batch):
        chunk = rows[i : i + batch]
        sb.table("vital_journal_daily").upsert(
            chunk, on_conflict="recorded_at"
        ).execute()
        print(f"upserted {i + len(chunk)}/{len(rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
