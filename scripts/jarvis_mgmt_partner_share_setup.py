#!/usr/bin/env python3
"""仲介パートナー共有 Drive フォルダの作成確認＋リンク共有（anyone with link / viewer）。

使用アカウント: admin（token_drive_admin_write.json · drive スコープ）
ローカル正本:
  GoogleDrive-admin@…/マイドライブ/【仲介パートナー共有】/

  cd ~/git-repos
  ~/selenium_env/venv/bin/python scripts/jarvis_mgmt_partner_share_setup.py --ensure-dirs
  ~/selenium_env/venv/bin/python scripts/jarvis_mgmt_partner_share_setup.py --share --apply
  ~/selenium_env/venv/bin/python scripts/jarvis_mgmt_partner_share_setup.py --auth-console
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
MANUAL = REPO / "215_kamiooya" / "C1_cursor" / "1b_Cursorマニュアル"
CREDENTIALS = MANUAL / "credentials.json"
TOKEN_WRITE = MANUAL / "token_drive_admin_write.json"
TOKEN_RO = MANUAL / "token_drive_admin.json"
CONFIG_PATH = REPO / "config" / "kurashift_mgmt_share_folders.yaml"
ENV_PRIVATE = REPO / ".env.jarvis_private"

GDRIVE_ROOT = Path.home() / (
    "Library/CloudStorage/GoogleDrive-admin@livingsupport-matsu.co.jp/マイドライブ"
)
SHARE_ROOT = GDRIVE_ROOT / "【仲介パートナー共有】"

# (relpath, share?, config_key)
FOLDERS: list[tuple[str, bool, str]] = [
    ("00_共通", True, "common"),
    ("10_北区_Grandole志賀本通", True, "kita_parent"),
    ("10_北区_Grandole志賀本通/Grandole志賀本通", True, "kita_grandole"),
    ("20_緑区_キャラメル", True, "midori_parent"),
    ("20_緑区_キャラメル/キャラメル", True, "midori_caramel"),
    ("90_運用メモ_非共有", False, "ops_private"),
]

SCOPES = ["https://www.googleapis.com/auth/drive"]


def ensure_dirs() -> list[str]:
    created: list[str] = []
    SHARE_ROOT.mkdir(parents=True, exist_ok=True)
    readmes = {
        "00_共通": "両エリア向け横断資料（AD方針・モデルルーム概要・LUUP等）",
        "10_北区_Grandole志賀本通/Grandole志賀本通": "募集チラシ＋周辺MAP（I/II 区分なし。鍵番号全文は載せない）",
        "20_緑区_キャラメル/キャラメル": "周辺MAPのみ（募集チラシ未作成のため。鍵番号全文は載せない）",
        "90_運用メモ_非共有": "リンク共有しない。Jarvis／運用メモ専用",
    }
    for rel, _share, _key in FOLDERS:
        p = SHARE_ROOT / rel
        if not p.is_dir():
            p.mkdir(parents=True, exist_ok=True)
            created.append(rel)
        tip = readmes.get(rel)
        if tip:
            readme = p / "README.txt"
            if not readme.is_file():
                readme.write_text(tip + "\n", encoding="utf-8")
    return created


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
        except Exception:
            creds = None
    if not creds or not creds.valid:
        if not CREDENTIALS.is_file():
            raise SystemExit(f"credentials.json がありません: {CREDENTIALS}")
        flow = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS), SCOPES)
        login_hint = "admin@livingsupport-matsu.co.jp"
        if auth_console:
            creds = flow.run_console(login_hint=login_hint)
        else:
            creds = flow.run_local_server(port=0, login_hint=login_hint)
        TOKEN_WRITE.write_text(creds.to_json(), encoding="utf-8")
        print(f"# wrote {TOKEN_WRITE}", file=sys.stderr)
    return creds


def drive_service(*, force_auth: bool = False, auth_console: bool = False):
    from googleapiclient.discovery import build

    return build(
        "drive",
        "v3",
        credentials=_creds(force_auth=force_auth, auth_console=auth_console),
        cache_discovery=False,
    )


def find_child(svc: Any, parent_id: str, name: str) -> str | None:
    q = (
        f"'{parent_id}' in parents and name = '{name.replace(chr(39), chr(92)+chr(39))}' "
        "and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
    )
    res = (
        svc.files()
        .list(q=q, spaces="drive", fields="files(id,name)", pageSize=5)
        .execute()
    )
    files = res.get("files") or []
    return files[0]["id"] if files else None


def ensure_remote_folder(svc: Any, parent_id: str, name: str) -> str:
    existing = find_child(svc, parent_id, name)
    if existing:
        return existing
    meta = {
        "name": name,
        "mimeType": "application/vnd.google-apps.folder",
        "parents": [parent_id],
    }
    created = svc.files().create(body=meta, fields="id,name").execute()
    return str(created["id"])


def set_anyone_reader(svc: Any, file_id: str) -> str:
    """Return webViewLink after ensuring anyoneWithLink reader."""
    try:
        svc.permissions().create(
            fileId=file_id,
            body={"type": "anyone", "role": "reader"},
            fields="id",
        ).execute()
    except Exception as exc:
        # already shared etc.
        msg = str(exc)
        if "alreadyExists" not in msg and "403" not in msg:
            # retry ignore duplicate
            if "duplicate" not in msg.lower():
                print(f"# permission warn {file_id}: {exc}", file=sys.stderr)
    meta = (
        svc.files()
        .get(fileId=file_id, fields="id,name,webViewLink")
        .execute()
    )
    return str(meta.get("webViewLink") or f"https://drive.google.com/drive/folders/{file_id}")


def find_root_share_id(svc: Any) -> str | None:
    q = (
        "name = '【仲介パートナー共有】' and mimeType = 'application/vnd.google-apps.folder' "
        "and trashed = false"
    )
    res = (
        svc.files()
        .list(q=q, spaces="drive", fields="files(id,name)", pageSize=10)
        .execute()
    )
    files = res.get("files") or []
    return files[0]["id"] if files else None


def share_all(*, apply: bool, force_auth: bool, auth_console: bool) -> dict[str, Any]:
    ensure_dirs()
    svc = drive_service(force_auth=force_auth, auth_console=auth_console)
    root_id = find_root_share_id(svc)
    if not root_id:
        # create under My Drive
        about = svc.about().get(fields="user,storageQuota").execute()
        print(f"# drive user={about.get('user',{}).get('emailAddress')}", file=sys.stderr)
        meta = {
            "name": "【仲介パートナー共有】",
            "mimeType": "application/vnd.google-apps.folder",
        }
        if apply:
            created = svc.files().create(body=meta, fields="id").execute()
            root_id = str(created["id"])
        else:
            return {"ok": False, "error": "root folder not found on Drive yet (sync pending?)"}

    # Build tree
    id_by_rel: dict[str, str] = {"": root_id}
    urls: dict[str, str] = {}
    for rel, do_share, key in FOLDERS:
        parts = rel.split("/")
        parent_rel = "/".join(parts[:-1])
        parent_id = id_by_rel[parent_rel]
        name = parts[-1]
        if apply:
            fid = ensure_remote_folder(svc, parent_id, name)
        else:
            fid = find_child(svc, parent_id, name) or f"dry-{rel}"
        id_by_rel[rel] = fid
        if do_share and apply and not str(fid).startswith("dry-"):
            urls[key] = set_anyone_reader(svc, fid)
        elif do_share:
            urls[key] = f"(pending) {rel}"

    # ルート全体は共有しない（90_運用メモ_非共有 が継承で公開されるのを防ぐ）

    cfg = {
        "account": "admin@livingsupport-matsu.co.jp",
        "local_root": str(SHARE_ROOT),
        "folder_ids": {k: id_by_rel.get(rel, "") for rel, _s, k in FOLDERS},
        "urls": urls,
        "template_defaults": {
            "common": urls.get("common", ""),
            "kita_shiga": urls.get("kita_parent") or urls.get("kita_grandole_i", ""),
            "midori_caramel": urls.get("midori_parent") or urls.get("midori_caramel", ""),
        },
    }
    if apply:
        CONFIG_PATH.write_text(
            __import__("yaml").safe_dump(cfg, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )
        _patch_env_urls(cfg["template_defaults"])
    return {"ok": True, "apply": apply, "config": cfg, "config_path": str(CONFIG_PATH)}


def _patch_env_urls(defaults: dict[str, str]) -> None:
    if not ENV_PRIVATE.is_file():
        return
    mapping = {
        "MGMT_SHARE_URL_COMMON": defaults.get("common") or "",
        "MGMT_SHARE_URL_KITA": defaults.get("kita_shiga") or "",
        "MGMT_SHARE_URL_MIDORI": defaults.get("midori_caramel") or "",
    }
    text = ENV_PRIVATE.read_text(encoding="utf-8")
    lines = text.splitlines()
    keys_done = set()
    out: list[str] = []
    for line in lines:
        replaced = False
        for k, v in mapping.items():
            if line.startswith(f"{k}=") or line.startswith(f"# {k}="):
                if v and not v.startswith("(pending)"):
                    out.append(f"{k}={v}")
                    keys_done.add(k)
                    replaced = True
                break
        if not replaced:
            out.append(line)
    for k, v in mapping.items():
        if k not in keys_done and v and not v.startswith("(pending)"):
            out.append(f"{k}={v}")
    if not text.endswith("\n"):
        out.append("")
    ENV_PRIVATE.write_text("\n".join(out) + ("\n" if out and out[-1] != "" else ""), encoding="utf-8")
    print("# updated .env.jarvis_private MGMT_SHARE_URL_*", file=sys.stderr)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ensure-dirs", action="store_true")
    ap.add_argument("--share", action="store_true")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--auth-console", action="store_true")
    ap.add_argument("--force-auth", action="store_true")
    args = ap.parse_args()

    if args.ensure_dirs or not args.share:
        created = ensure_dirs()
        print(json.dumps({"ok": True, "created": created, "root": str(SHARE_ROOT)}, ensure_ascii=False))
        if not args.share:
            return 0

    out = share_all(
        apply=bool(args.apply),
        force_auth=bool(args.force_auth),
        auth_console=bool(args.auth_console),
    )
    # redact nothing — URLs are intentionally shareable
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0 if out.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
