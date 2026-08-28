"""KURASHIFT S1 証憑 — admin Drive API アップロード（D3）。

token_drive_admin_write.json（drive フルスコープ）を使用。
公開リンクは付けない（admin マイドライブ内のみ）。

  from jarvis_kurashift_evidence_gdrive import upload_evidence_file, verify_drive_api
"""
from __future__ import annotations

import json
import mimetypes
import os
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
MANUAL = REPO / "215_kamiooya" / "C1_cursor" / "1b_Cursorマニュアル"
CREDENTIALS = MANUAL / "credentials.json"
TOKEN_WRITE = MANUAL / "token_drive_admin_write.json"
STATE_PATH = REPO / ".jarvis_state" / "kurashift_evidence_drive_folders.json"

EVIDENCE_ROOT_NAME = "KURASHIFT_問合せ証憑"
PARENT_FOLDER_NAME = "230_物件調査"
SCOPES = ["https://www.googleapis.com/auth/drive"]
LOGIN_HINT = "admin@livingsupport-matsu.co.jp"


def drive_api_disabled() -> bool:
    return os.environ.get("KURASHIFT_EVIDENCE_DRIVE_API_DISABLE", "").strip() in (
        "1",
        "true",
        "yes",
    )


def _load_folder_state() -> dict[str, str]:
    if not STATE_PATH.is_file():
        return {}
    try:
        raw = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        return {str(k): str(v) for k, v in (raw.get("deal_folders") or {}).items()}
    except Exception:
        return {}


def _save_folder_state(deal_folders: dict[str, str]) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "deal_folders": deal_folders,
        "evidence_root_name": EVIDENCE_ROOT_NAME,
        "parent_folder_name": PARENT_FOLDER_NAME,
    }
    STATE_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _creds(*, force_auth: bool = False, auth_console: bool = False):
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow

    creds = None
    if TOKEN_WRITE.is_file() and not force_auth:
        creds = Credentials.from_authorized_user_file(str(TOKEN_WRITE), SCOPES)
    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            TOKEN_WRITE.write_text(creds.to_json(), encoding="utf-8")
        except Exception:
            creds = None
    if not creds or not creds.valid:
        if not CREDENTIALS.is_file():
            raise FileNotFoundError(f"credentials.json がありません: {CREDENTIALS}")
        flow = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS), SCOPES)
        if auth_console:
            creds = flow.run_console(login_hint=LOGIN_HINT)
        else:
            creds = flow.run_local_server(port=0, login_hint=LOGIN_HINT)
        TOKEN_WRITE.write_text(creds.to_json(), encoding="utf-8")
    return creds


def drive_service(*, force_auth: bool = False, auth_console: bool = False):
    from googleapiclient.discovery import build

    return build(
        "drive",
        "v3",
        credentials=_creds(force_auth=force_auth, auth_console=auth_console),
        cache_discovery=False,
    )


def _escape_q(s: str) -> str:
    return s.replace("'", "\\'")


def find_child_folder(svc: Any, parent_id: str, name: str) -> str | None:
    q = (
        f"'{parent_id}' in parents and name = '{_escape_q(name)}' "
        "and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
    )
    res = (
        svc.files()
        .list(q=q, spaces="drive", fields="files(id,name)", pageSize=5)
        .execute()
    )
    files = res.get("files") or []
    return str(files[0]["id"]) if files else None


def ensure_folder(svc: Any, parent_id: str, name: str) -> str:
    existing = find_child_folder(svc, parent_id, name)
    if existing:
        return existing
    meta = {
        "name": name,
        "mimeType": "application/vnd.google-apps.folder",
        "parents": [parent_id],
    }
    created = svc.files().create(body=meta, fields="id,name").execute()
    return str(created["id"])


def ensure_evidence_deal_folder(svc: Any, deal_id: str) -> str:
    cached = _load_folder_state()
    if deal_id in cached:
        return cached[deal_id]

    root_meta = (
        svc.files()
        .get(fileId="root", fields="id")
        .execute()
    )
    my_drive = str(root_meta["id"])

    parent_id = find_child_folder(svc, my_drive, PARENT_FOLDER_NAME)
    if not parent_id:
        parent_id = ensure_folder(svc, my_drive, PARENT_FOLDER_NAME)

    evidence_root_id = find_child_folder(svc, parent_id, EVIDENCE_ROOT_NAME)
    if not evidence_root_id:
        evidence_root_id = ensure_folder(svc, parent_id, EVIDENCE_ROOT_NAME)

    deal_folder_id = ensure_folder(svc, evidence_root_id, deal_id)
    cached[deal_id] = deal_folder_id
    _save_folder_state(cached)
    return deal_folder_id


def find_file_in_folder(svc: Any, folder_id: str, filename: str) -> str | None:
    q = (
        f"'{folder_id}' in parents and name = '{_escape_q(filename)}' "
        "and trashed = false"
    )
    res = (
        svc.files()
        .list(q=q, spaces="drive", fields="files(id,name)", pageSize=5)
        .execute()
    )
    files = res.get("files") or []
    return str(files[0]["id"]) if files else None


def upload_evidence_file(
    local_path: Path,
    deal_id: str,
    *,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Upload local evidence file to admin Drive. Returns drive_file_id / webViewLink."""
    if drive_api_disabled():
        return {"ok": True, "skipped": "drive_api_disabled"}

    local_path = local_path.resolve()
    if not local_path.is_file():
        return {"ok": False, "error": f"file not found: {local_path}"}

    if dry_run:
        return {
            "ok": True,
            "dry_run": True,
            "deal_id": deal_id,
            "filename": local_path.name,
            "local_path": str(local_path),
        }

    from googleapiclient.http import MediaFileUpload

    svc = drive_service()
    folder_id = ensure_evidence_deal_folder(svc, deal_id)
    filename = local_path.name
    existing_id = find_file_in_folder(svc, folder_id, filename)
    mime, _ = mimetypes.guess_type(filename)
    mime = mime or "application/octet-stream"
    media = MediaFileUpload(str(local_path), mimetype=mime, resumable=False)

    if existing_id:
        updated = (
            svc.files()
            .update(
                fileId=existing_id,
                media_body=media,
                fields="id,name,webViewLink,size",
            )
            .execute()
        )
        file_id = str(updated["id"])
        web_link = str(updated.get("webViewLink") or "")
    else:
        meta = {"name": filename, "parents": [folder_id]}
        created = (
            svc.files()
            .create(body=meta, media_body=media, fields="id,name,webViewLink,size")
            .execute()
        )
        file_id = str(created["id"])
        web_link = str(created.get("webViewLink") or "")

    if not web_link:
        web_link = f"https://drive.google.com/file/d/{file_id}/view"

    return {
        "ok": True,
        "deal_id": deal_id,
        "filename": filename,
        "drive_file_id": file_id,
        "drive_web_view_link": web_link,
        "drive_folder_id": folder_id,
    }


def verify_drive_api(*, cleanup: bool = True) -> dict[str, Any]:
    """Smoke: folder ensure + tiny upload + optional delete."""
    if drive_api_disabled():
        return {"ok": False, "error": "drive_api_disabled"}

    import tempfile

    deal_id = "_drive_api_verify"
    with tempfile.NamedTemporaryFile(
        suffix=".png", delete=False, prefix="kurashift_evidence_verify_"
    ) as tmp:
        tmp.write(
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
            b"\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDAT"
            b"x\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
        )
        tmp_path = Path(tmp.name)

    try:
        up = upload_evidence_file(tmp_path, deal_id, dry_run=False)
        if not up.get("ok"):
            return up
        file_id = up.get("drive_file_id")
        if cleanup and file_id:
            svc = drive_service()
            svc.files().delete(fileId=str(file_id)).execute()
            up["cleaned_up"] = True
        up["verify"] = True
        return up
    finally:
        tmp_path.unlink(missing_ok=True)


def main() -> int:
    import argparse

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--verify", action="store_true", help="Drive API 接続・upload スモーク")
    ap.add_argument("--upload", metavar="PATH")
    ap.add_argument("--deal-id", default="")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if args.verify:
        print(json.dumps(verify_drive_api(), ensure_ascii=False, indent=2))
        return 0
    if args.upload:
        if not args.deal_id:
            print("--deal-id required", file=sys.stderr)
            return 2
        print(
            json.dumps(
                upload_evidence_file(
                    Path(args.upload), args.deal_id.strip(), dry_run=args.dry_run
                ),
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    ap.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
