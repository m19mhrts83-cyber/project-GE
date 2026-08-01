#!/usr/bin/env python3
"""OneDrive 連絡先一覧.yaml → Dashboard 用 partner_contacts.json を更新。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "apps/jarvis-dashboard/config/partner_contacts.json"
ONEDRIVE = (
    Path.home()
    / "Library/CloudStorage/OneDrive-個人用/215_神・大家さん倶楽部"
    / "C2_ルーティン作業/26_パートナー社への相談/000_共通/連絡先一覧.yaml"
)


def main() -> int:
    try:
        import yaml
    except ImportError:
        print("PyYAML required", file=sys.stderr)
        return 1
    if not ONEDRIVE.is_file():
        print(f"missing {ONEDRIVE}", file=sys.stderr)
        return 1
    data = yaml.safe_load(ONEDRIVE.read_text(encoding="utf-8"))
    partners = data.get("partners") or []
    out = []
    for p in partners:
        emails = [str(e).strip() for e in (p.get("emails") or []) if str(e).strip() and "@" in str(e)]
        phones = [str(x).strip() for x in (p.get("phones") or []) if str(x).strip()]
        if not emails and not phones:
            continue
        out.append(
            {
                "name": p.get("name") or "",
                "folder": p.get("folder") or "",
                "emails": emails,
                "phones": phones,
                "via_ambiguous": bool(emails and phones),
            }
        )
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        json.dumps({"version": 1, "partners": out}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"# wrote {OUT} n={len(out)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
