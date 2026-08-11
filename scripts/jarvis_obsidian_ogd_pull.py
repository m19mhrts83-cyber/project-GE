#!/usr/bin/env python3
"""Pull OGD-tagged Drive files into the Documents vault.

iPhone Push writes tagged files. Mac Obsidian is rarely opened, so Jarvis
downloads those files here before reading Journal / on 「同期して」.

Never overwrites a local file that is newer than Drive (conflict line).
Never prints tokens.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests

VAULT_NAME = "500_Obsidian_r1"
VAULT = Path.home() / "Documents/500_Obsidian_r1"
DATA_JSON = VAULT / ".obsidian/plugins/google-drive-sync/data.json"
ACCESS_URL = "https://ogd.richardxiong.com/api/access"
DRIVE = "https://www.googleapis.com/drive/v3/files"
SKIP_PREFIXES = (".obsidian/plugins/google-drive-sync/",)
FOLDER_MIME = "application/vnd.google-apps.folder"


def access_token(refresh_token: str) -> str:
    r = requests.post(ACCESS_URL, json={"refresh_token": refresh_token}, timeout=30)
    r.raise_for_status()
    token = r.json().get("access_token")
    if not token:
        raise SystemExit("no access_token from OGD")
    return token


def parse_rfc3339(value: str | None) -> datetime | None:
    if not value:
        return None
    text = value.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def local_mtime(path: Path) -> datetime:
    return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)


def md5_bytes(data: bytes) -> str:
    return hashlib.md5(data).hexdigest()


def list_tagged(session: requests.Session, prefix: str | None) -> list[dict]:
    out: list[dict] = []
    page = None
    query = (
        "trashed=false"
        f" and properties has {{ key='vault' and value='{VAULT_NAME}' }}"
        f" and mimeType != '{FOLDER_MIME}'"
    )
    while True:
        params = {
            "q": query,
            "fields": "nextPageToken,files(id,name,mimeType,modifiedTime,md5Checksum,properties,size)",
            "pageSize": 100,
        }
        if page:
            params["pageToken"] = page
        r = session.get(DRIVE, params=params, timeout=60)
        r.raise_for_status()
        data = r.json()
        for f in data.get("files") or []:
            path = (f.get("properties") or {}).get("path") or ""
            if not path or path.startswith(SKIP_PREFIXES):
                continue
            if prefix and not path.startswith(prefix):
                continue
            out.append(f)
        page = data.get("nextPageToken")
        if not page:
            break
    return out


def download_bytes(session: requests.Session, file_id: str) -> bytes:
    r = session.get(f"{DRIVE}/{file_id}", params={"alt": "media"}, timeout=120)
    r.raise_for_status()
    return r.content


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--prefix",
        default="",
        help="Vault-relative prefix, e.g. 01_Journaling/★Journal",
    )
    args = parser.parse_args()
    prefix = args.prefix or None

    raw = json.loads(DATA_JSON.read_text())
    refresh = raw.get("refreshToken") or ""
    if not refresh:
        print("missing refreshToken in data.json", file=sys.stderr)
        return 1

    session = requests.Session()
    session.headers["Authorization"] = f"Bearer {access_token(refresh)}"

    files = list_tagged(session, prefix)
    pulled = 0
    skipped = 0
    conflicts = 0
    mapping = raw.setdefault("driveIdToPath", {})

    for f in files:
        path = (f.get("properties") or {}).get("path") or ""
        local = VAULT / path
        drive_mtime = parse_rfc3339(f.get("modifiedTime"))
        drive_md5 = (f.get("md5Checksum") or "").lower()

        if local.is_file():
            local_md5 = md5_bytes(local.read_bytes())
            if drive_md5 and local_md5 == drive_md5:
                skipped += 1
                mapping[f["id"]] = path
                continue
            if drive_mtime and local_mtime(local) > drive_mtime:
                print(f"conflict {path}")
                conflicts += 1
                continue
            action = "update"
        else:
            action = "create"

        print(f"{'would-' + action if args.dry_run else action:7} {path}")
        if args.dry_run:
            pulled += 1
            continue
        data = download_bytes(session, f["id"])
        local.parent.mkdir(parents=True, exist_ok=True)
        local.write_bytes(data)
        mapping[f["id"]] = path
        pulled += 1

    if not args.dry_run:
        DATA_JSON.write_text(json.dumps(raw, ensure_ascii=False, indent=2) + "\n")

    print(
        f"pulled={pulled} unchanged={skipped} conflicts={conflicts} listed={len(files)}"
    )
    return 1 if conflicts else 0


if __name__ == "__main__":
    raise SystemExit(main())
