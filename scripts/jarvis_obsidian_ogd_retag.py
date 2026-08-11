#!/usr/bin/env python3
"""Make Cursor/Finder notes visible to Google Drive Sync (OGD / iPhone).

OGD uses drive.file scope: it can only see files the plugin created.
Files written via Finder or Cursor into Google Drive Desktop are in the
same folder but invisible to OGD, so iPhone Pull skips them.

This script uploads local Documents copies *through the OGD token* with
properties.vault + properties.path, then updates data.json maps.
Never prints tokens.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import requests

VAULT_NAME = "500_Obsidian_r1"
VAULT = Path.home() / "Documents/500_Obsidian_r1"
DATA_JSON = VAULT / ".obsidian/plugins/google-drive-sync/data.json"
ACCESS_URL = "https://ogd.richardxiong.com/api/access"
DRIVE = "https://www.googleapis.com/drive/v3/files"
UPLOAD = "https://www.googleapis.com/upload/drive/v3/files"

# Known OGD-visible parents (plugin-created folders)
PARENTS = {
    "03_Literature Note(まとめノート)": "1dlmEL2neWf9sYGj8aMT8v5HiHP-NbSBl",
    "03_Literature Note(まとめノート)/家族,Yearly": "1JyxCNDj0gUZbnL0HKIVC4MxdU8XxAvB-",
    "02_Clippings/D_Knowledge_Method/RAIMO講座": "1-nmBssX3SJvDihMwJOnIYG5_gafFFdzk",
    "01_Journaling/Obsidianなどの知識管理": "1GfWVtloAxqEnhcU4GlpPc2HrSy9ZVQvr",
}

WANT_PATHS = [
    "03_Literature Note(まとめノート)/家族,Yearly/家族お出かけ_20260813_ホワイトウェイブ21.md",
    "03_Literature Note(まとめノート)/家族,Yearly/家族お出かけ_20260814_名古屋市美術館_HARBS.md",
    "03_Literature Note(まとめノート)/ETC割引確認_Phase1サマリー.md",
    "03_Literature Note(まとめノート)/ETC割引確認_実施計画.md",
    "03_Literature Note(まとめノート)/OraMemoRing_Watch外し睡眠運用.md",
    "03_Literature Note(まとめノート)/給与振込4口座_Oliveメイン化_サマリー.md",
    "03_Literature Note(まとめノート)/研修,Yearly/大阪ワクワクMG_20260815-16.md",
    "02_Clippings/D_Knowledge_Method/RAIMO講座/AIリスキリング講座を聞いて.md",
]


def access_token(refresh_token: str) -> str:
    r = requests.post(ACCESS_URL, json={"refresh_token": refresh_token}, timeout=30)
    r.raise_for_status()
    token = r.json().get("access_token")
    if not token:
        raise SystemExit("no access_token from OGD")
    return token


def ogd_get(session: requests.Session, file_id: str) -> dict | None:
    r = session.get(
        f"{DRIVE}/{file_id}",
        params={"fields": "id,name,properties,parents"},
        timeout=30,
    )
    if r.status_code == 404:
        return None
    r.raise_for_status()
    return r.json()


def find_by_path(session: requests.Session, path: str) -> dict | None:
    r = session.get(
        DRIVE,
        params={
            "q": f"trashed=false and properties has {{ key='path' and value='{path}' }}",
            "fields": "files(id,name,properties,md5Checksum)",
        },
        timeout=30,
    )
    r.raise_for_status()
    files = r.json().get("files") or []
    return files[0] if files else None


def create_folder(session: requests.Session, name: str, parent_id: str, path: str) -> str:
    r = session.post(
        DRIVE,
        json={
            "name": name,
            "mimeType": "application/vnd.google-apps.folder",
            "parents": [parent_id],
            "properties": {"vault": VAULT_NAME, "path": path},
        },
        timeout=30,
    )
    r.raise_for_status()
    return r.json()["id"]


def ensure_parent(session: requests.Session, parent_path: str) -> str:
    if parent_path in PARENTS:
        fid = PARENTS[parent_path]
        if ogd_get(session, fid):
            return fid
    existing = find_by_path(session, parent_path)
    if existing:
        PARENTS[parent_path] = existing["id"]
        return existing["id"]
    # create under grandparent
    name = Path(parent_path).name
    gp = str(Path(parent_path).parent)
    gp_id = ensure_parent(session, gp) if gp != "." else None
    if not gp_id:
        raise SystemExit(f"cannot create folder, missing parent: {parent_path}")
    print(f"mkdir  {parent_path}")
    new_id = create_folder(session, name, gp_id, parent_path)
    PARENTS[parent_path] = new_id
    return new_id


def upload_file(session: requests.Session, local: Path, parent_id: str, vault_path: str) -> str:
    meta = {
        "name": local.name,
        "mimeType": "text/markdown",
        "parents": [parent_id],
        "properties": {"vault": VAULT_NAME, "path": vault_path},
    }
    boundary = "=======ogd_jarvis======="
    body = (
        f"--{boundary}\r\n"
        "Content-Type: application/json; charset=UTF-8\r\n\r\n"
        f"{json.dumps(meta, ensure_ascii=False)}\r\n"
        f"--{boundary}\r\n"
        "Content-Type: text/markdown\r\n\r\n"
    ).encode("utf-8") + local.read_bytes() + f"\r\n--{boundary}--".encode("ascii")
    r = session.post(
        UPLOAD,
        params={"uploadType": "multipart", "fields": "id,name,properties"},
        headers={"Content-Type": f"multipart/related; boundary={boundary}"},
        data=body,
        timeout=60,
    )
    r.raise_for_status()
    return r.json()["id"]


def update_file(session: requests.Session, file_id: str, local: Path, vault_path: str) -> str:
    meta = {
        "name": local.name,
        "mimeType": "text/markdown",
        "properties": {"vault": VAULT_NAME, "path": vault_path},
    }
    boundary = "=======ogd_jarvis======="
    body = (
        f"--{boundary}\r\n"
        "Content-Type: application/json; charset=UTF-8\r\n\r\n"
        f"{json.dumps(meta, ensure_ascii=False)}\r\n"
        f"--{boundary}\r\n"
        "Content-Type: text/markdown\r\n\r\n"
    ).encode("utf-8") + local.read_bytes() + f"\r\n--{boundary}--".encode("ascii")
    r = session.patch(
        f"{UPLOAD}/{file_id}",
        params={"uploadType": "multipart", "fields": "id,name,properties"},
        headers={"Content-Type": f"multipart/related; boundary={boundary}"},
        data=body,
        timeout=60,
    )
    r.raise_for_status()
    return r.json()["id"]


def _local_md5(path: Path) -> str:
    return hashlib.md5(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "paths",
        nargs="*",
        help="Vault-relative paths to upload. If omitted, uses the built-in WANT_PATHS list.",
    )
    args = parser.parse_args()
    want = list(args.paths) if args.paths else list(WANT_PATHS)

    raw = json.loads(DATA_JSON.read_text())
    refresh = raw.get("refreshToken") or ""
    if not refresh:
        print("missing refreshToken in data.json", file=sys.stderr)
        return 1

    session = requests.Session()
    session.headers["Authorization"] = f"Bearer {access_token(refresh)}"

    created: dict[str, str] = {}
    updated: dict[str, str] = {}
    already = 0
    missing_local = []

    for path in want:
        local = VAULT / path
        if not local.is_file():
            missing_local.append(path)
            continue
        hit = find_by_path(session, path)
        if hit:
            drive_md5 = (hit.get("md5Checksum") or "").lower()
            if drive_md5 and drive_md5 == _local_md5(local):
                print(f"ok      {path}")
                already += 1
                continue
            print(f"{'would-up' if args.dry_run else 'update '} {path}")
            if args.dry_run:
                updated[path] = hit["id"]
                continue
            update_file(session, hit["id"], local, path)
            updated[path] = hit["id"]
            continue
        parent_path = str(Path(path).parent)
        print(f"{'would-up' if args.dry_run else 'upload '} {path}")
        if args.dry_run:
            continue
        parent_id = ensure_parent(session, parent_path)
        new_id = upload_file(session, local, parent_id, path)
        created[path] = new_id

    if not args.dry_run and (created or updated):
        mapping = raw.setdefault("driveIdToPath", {})
        ops = raw.setdefault("operations", {})
        for path, fid in {**created, **updated}.items():
            mapping[fid] = path
            if ops.get(path) in ("create", "modify"):
                del ops[path]
        if ops.get("03_Literature Note(まとめノート)/研修,Yearly") == "create":
            del ops["03_Literature Note(まとめノート)/研修,Yearly"]
        DATA_JSON.write_text(json.dumps(raw, ensure_ascii=False, indent=2) + "\n")

    print(
        f"uploaded={len(created)} updated={len(updated)} "
        f"already_ok={already} missing_local={len(missing_local)}"
    )
    for m in missing_local:
        print(f"missing {m}")
    return 0 if not missing_local else 2


if __name__ == "__main__":
    raise SystemExit(main())
