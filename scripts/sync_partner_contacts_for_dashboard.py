#!/usr/bin/env python3
"""OneDrive 連絡先一覧.yaml → Dashboard 用 partner_contacts.json を更新。

PRIVATE_EMAIL_FOLDERS の宛先は公開リポに置かない（2026-11-21 松野さん了承）。
公開側の partner_contacts.json では emails を空にし、実値は ignore 済みの
partner_contacts.private.json（config/private_paths.txt・非公開リポへ写す）に書く。
Vercel では同じ JSON を環境変数 PARTNER_CONTACTS_PRIVATE_JSON に入れる。
"""
from __future__ import annotations

import json
import sys
import unicodedata
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "apps/jarvis-dashboard/config/partner_contacts.json"
PRIVATE_OUT = REPO / "apps/jarvis-dashboard/config/partner_contacts.private.json"
# 宛先を公開しない連絡先（folder 名）。事務局アドレスなど
PRIVATE_EMAIL_FOLDERS = {"P809_神大家運営回答"}
ONEDRIVE = (
    Path.home()
    / "Library/CloudStorage/OneDrive-個人用/215_神・大家さん倶楽部"
    / "C2_ルーティン作業/26_パートナー社への相談/000_共通/連絡先一覧.yaml"
)


def is_private_folder(folder: str) -> bool:
    return unicodedata.normalize("NFC", folder or "") in PRIVATE_EMAIL_FOLDERS


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
    private: dict[str, list[str]] = {}
    for p in partners:
        emails = [str(e).strip() for e in (p.get("emails") or []) if str(e).strip() and "@" in str(e)]
        phones = [str(x).strip() for x in (p.get("phones") or []) if str(x).strip()]
        if not emails and not phones:
            continue
        row = {
            "name": p.get("name") or "",
            "folder": p.get("folder") or "",
            "emails": emails,
            "phones": phones,
            "via_ambiguous": bool(emails and phones),
        }
        if is_private_folder(row["folder"]) and emails:
            private[row["folder"]] = emails
            row["emails"] = []
            row["emails_private"] = True
        out.append(row)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        json.dumps({"version": 1, "partners": out}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"# wrote {OUT} n={len(out)}")
    if private:
        PRIVATE_OUT.write_text(
            json.dumps({"version": 1, "emails_by_folder": private}, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"# wrote {PRIVATE_OUT} n={len(private)}（公開しない宛先）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
