#!/usr/bin/env python3
"""OneDrive 連絡先一覧.yaml → Dashboard 用の連絡先ミラーを更新。

公開リポに置くのは folder・name・via_ambiguous だけ（2026-11-21 松野さん了承）。
メール・電話の実値は ignore 済みの partner_contacts.private.json にだけ書く
（config/private_paths.txt・非公開リポへ写す）。Vercel では同じ JSON を環境変数
PARTNER_CONTACTS_PRIVATE_JSON に入れる。

- 公開側 partner_contacts.json は「すでに載っている取引先」の行だけ更新する。
  OneDrive にだけある新規の取引先は公開 JSON に入れず、private の extra_partners へ。
- private は yaml にある folder だけ上書きし、yaml に無い folder の既存値は残す。
"""
from __future__ import annotations

import json
import sys
import unicodedata
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "apps/jarvis-dashboard/config/partner_contacts.json"
PRIVATE_OUT = REPO / "apps/jarvis-dashboard/config/partner_contacts.private.json"
ONEDRIVE = (
    Path.home()
    / "Library/CloudStorage/OneDrive-個人用/215_神・大家さん倶楽部"
    / "C2_ルーティン作業/26_パートナー社への相談/000_共通/連絡先一覧.yaml"
)


def nfc(s: str) -> str:
    return unicodedata.normalize("NFC", s or "")


def _load_json(path: Path) -> dict:
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def build(partners: list[dict], public_old: dict, private_old: dict) -> tuple[dict, dict]:
    """(公開 JSON, 非公開 JSON) を返す。純関数（テスト用）。"""
    known = {nfc(str(p.get("folder") or "")) for p in (public_old.get("partners") or [])}
    pub_rows: dict[str, dict] = {nfc(str(p.get("folder") or "")): dict(p) for p in (public_old.get("partners") or [])}
    emails_by = {nfc(k): list(v) for k, v in (private_old.get("emails_by_folder") or {}).items()}
    phones_by = {nfc(k): list(v) for k, v in (private_old.get("phones_by_folder") or {}).items()}
    extras = {nfc(str(e.get("folder") or "")): dict(e) for e in (private_old.get("extra_partners") or []) if isinstance(e, dict)}
    for p in partners:
        folder = nfc(str(p.get("folder") or ""))
        name = str(p.get("name") or "")
        emails = [str(e).strip() for e in (p.get("emails") or []) if str(e).strip() and "@" in str(e)]
        phones = [str(x).strip() for x in (p.get("phones") or []) if str(x).strip()]
        if not folder or (not emails and not phones):
            continue
        if emails:
            emails_by[folder] = emails
        else:
            emails_by.pop(folder, None)
        if phones:
            phones_by[folder] = phones
        else:
            phones_by.pop(folder, None)
        if folder in known:
            row = pub_rows[folder]
            row["name"] = name or row.get("name", "")
            row["emails"] = []
            row["phones"] = []
            row["via_ambiguous"] = bool(emails and phones)
            row["emails_private"] = bool(emails)
            row["phones_private"] = bool(phones)
        else:
            extras[folder] = {"name": name, "folder": folder}
    # 公開側は連絡先を空にした行だけ。既存行に実値が残っていても必ず落とす
    out_rows = []
    for folder, row in pub_rows.items():
        emails_private = bool(row.get("emails_private")) or bool(row.get("emails"))
        phones_private = bool(row.get("phones_private")) or bool(row.get("phones"))
        # 既存行に実値が残っていた場合は private へ退避
        if row.get("emails") and folder not in emails_by:
            emails_by[folder] = [str(e) for e in row["emails"]]
        if row.get("phones") and folder not in phones_by:
            phones_by[folder] = [str(x) for x in row["phones"]]
        out_rows.append({
            "name": row.get("name", ""),
            "folder": row.get("folder", folder),
            "emails": [],
            "phones": [],
            "via_ambiguous": bool(row.get("via_ambiguous")),
            "emails_private": emails_private,
            "phones_private": phones_private,
        })
    private = {"version": 1, "emails_by_folder": emails_by, "phones_by_folder": phones_by}
    ex = [e for f, e in extras.items() if f not in known]
    if ex:
        private["extra_partners"] = ex
    return {"version": 1, "partners": out_rows}, private


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
    pub, private = build(data.get("partners") or [], _load_json(OUT), _load_json(PRIVATE_OUT))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(pub, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    PRIVATE_OUT.write_text(json.dumps(private, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"# wrote {OUT} n={len(pub['partners'])}（連絡先なし）")
    print(
        f"# wrote {PRIVATE_OUT} emails={len(private['emails_by_folder'])} "
        f"phones={len(private['phones_by_folder'])} extra={len(private.get('extra_partners', []))}（公開しない）"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
