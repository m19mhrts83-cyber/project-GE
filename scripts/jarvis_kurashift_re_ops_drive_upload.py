#!/usr/bin/env python3
"""神大家割当 Drive（1162.松野 真治）へ物件フォルダ作成＋資料アップロード。

運営相談フォームの「資料格納場所」はここ（自分用証憑 Drive ではない）。

  cd ~/git-repos && set -a && source .env.jarvis_private && set +a
  ~/selenium_env/venv/bin/python scripts/jarvis_kurashift_re_ops_drive_upload.py \\
    --deal-id <uuid> --apply
  # 下書きの drive_folder / property_name も更新: --update-deal
"""
from __future__ import annotations

import argparse
import json
import mimetypes
import os
import re
import sys
from pathlib import Path
from typing import Any

import yaml
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

REPO = Path(__file__).resolve().parents[1]
PIPELINE_YAML = REPO / "config" / "kurashift_re_purchase_pipeline.yaml"
STATE_PATH = REPO / ".jarvis_state" / "kamiooya_ops_drive.json"
MANUAL = REPO / "215_kamiooya" / "C1_cursor" / "1b_Cursorマニュアル"
ATTACH_ROOT = REPO / ".jarvis_state" / "kurashift_re_deal_attachments"
EVIDENCE_ROOT = (
    Path.home()
    / "Library/CloudStorage/GoogleDrive-admin@livingsupport-matsu.co.jp"
    / "マイドライブ/230_物件調査/KURASHIFT_問合せ証憑"
)


def sb_client() -> Any:
    url = os.environ.get("JARVIS_SUPABASE_URL")
    key = os.environ.get("JARVIS_SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        raise SystemExit("JARVIS_SUPABASE_URL / JARVIS_SUPABASE_SERVICE_ROLE_KEY が必要です")
    from supabase import create_client

    return create_client(url, key)


def load_pipeline() -> dict[str, Any]:
    return yaml.safe_load(PIPELINE_YAML.read_text(encoding="utf-8")) or {}


def load_state() -> dict[str, Any]:
    if STATE_PATH.is_file():
        try:
            return json.loads(STATE_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def save_state(data: dict[str, Any]) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def drive_service(token_name: str) -> Any:
    token_path = MANUAL / token_name
    if not token_path.is_file():
        raise SystemExit(f"token がありません: {token_path}")
    creds = Credentials.from_authorized_user_file(str(token_path))
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        token_path.write_text(creds.to_json(), encoding="utf-8")
    return build("drive", "v3", credentials=creds, cache_discovery=False)


def list_child_folders(svc: Any, parent_id: str) -> list[dict[str, str]]:
    kw = dict(supportsAllDrives=True, includeItemsFromAllDrives=True)
    out: list[dict[str, str]] = []
    page = None
    q = (
        f"'{parent_id}' in parents and trashed=false "
        "and mimeType='application/vnd.google-apps.folder'"
    )
    while True:
        resp = (
            svc.files()
            .list(
                q=q,
                fields="nextPageToken,files(id,name)",
                pageSize=100,
                pageToken=page,
                **kw,
            )
            .execute()
        )
        for f in resp.get("files") or []:
            out.append({"id": str(f["id"]), "name": str(f["name"])})
        page = resp.get("nextPageToken")
        if not page:
            break
    return out


def next_folder_number(folders: list[dict[str, str]]) -> int:
    nums: list[float] = []
    for f in folders:
        m = re.match(r"^(\d+(?:\.\d+)?)_", f["name"])
        if m:
            nums.append(float(m.group(1)))
    return int(max(nums)) + 1 if nums else 1


def strip_grok_prefix(title: str) -> str:
    t = str(title or "").strip()
    t = re.sub(r"^\[Grok調査\]\s*", "", t)
    t = re.sub(r"^【Grok調査】\s*", "", t)
    return t.strip() or t


def suggest_folder_name(deal: dict[str, Any], next_n: int) -> str:
    title = strip_grok_prefix(str(deal.get("title") or ""))
    # スペース短縮
    short = re.sub(r"\s+", "", title)[:40] or "物件"
    price = deal.get("price_man")
    area = str(deal.get("area") or "").strip()
    pref_city = area or "所在未定"
    if price is not None:
        return f"{next_n}_{short}_{price}万({pref_city})"
    return f"{next_n}_{short}({pref_city})"


def source_dir(deal_id: str) -> Path:
    evidence = EVIDENCE_ROOT / deal_id
    if evidence.is_dir() and any(evidence.iterdir()):
        return evidence
    local = ATTACH_ROOT / deal_id
    if local.is_dir() and any(local.iterdir()):
        return local
    raise SystemExit(f"添付ソースがありません: {evidence} / {local}")


def upload_folder(
    *,
    deal: dict[str, Any],
    dry_run: bool,
) -> dict[str, Any]:
    pipe = load_pipeline()
    cfg = pipe.get("kamiooya_ops_drive") or {}
    root_id = str(cfg.get("root_folder_id") or "")
    token_name = str(cfg.get("token_name") or "token_google_workspace_estate.json")
    if not root_id:
        raise SystemExit("pipeline YAML に root_folder_id がありません")

    deal_id = str(deal.get("id") or "")
    state = load_state()
    deals_state = dict(state.get("deals") or {})
    cached = deals_state.get(deal_id) if isinstance(deals_state.get(deal_id), dict) else None

    svc = drive_service(token_name)
    children = list_child_folders(svc, root_id)
    # 既存ヒット（タイトルキーワード）
    title = strip_grok_prefix(str(deal.get("title") or ""))
    keys = [k for k in re.split(r"[\s　_/]+", title) if len(k) >= 2][:3]
    hit = None
    if cached and cached.get("folder_id"):
        hit = {"id": cached["folder_id"], "name": cached.get("folder_name") or ""}
    if not hit:
        for f in children:
            if any(k in f["name"] for k in keys if k):
                hit = f
                break

    nxt = next_folder_number(children)
    folder_name = suggest_folder_name(deal, nxt)
    src = source_dir(deal_id)
    pdfs = sorted(
        p for p in src.iterdir() if p.is_file() and not p.name.startswith(".")
    )

    if dry_run:
        return {
            "ok": True,
            "dry_run": True,
            "folder_name": hit["name"] if hit else folder_name,
            "folder_id": hit["id"] if hit else None,
            "files": [p.name for p in pdfs],
            "root_url": cfg.get("root_url"),
        }

    if hit:
        dest_id = str(hit["id"])
        dest_name = str(hit["name"] or folder_name)
    else:
        meta = (
            svc.files()
            .create(
                body={
                    "name": folder_name,
                    "mimeType": "application/vnd.google-apps.folder",
                    "parents": [root_id],
                },
                fields="id,name,webViewLink",
                supportsAllDrives=True,
            )
            .execute()
        )
        dest_id = str(meta["id"])
        dest_name = str(meta["name"])

    # 既存ファイル名
    exist: set[str] = set()
    page = None
    kw = dict(supportsAllDrives=True, includeItemsFromAllDrives=True)
    while True:
        resp = (
            svc.files()
            .list(
                q=f"'{dest_id}' in parents and trashed=false",
                fields="nextPageToken,files(name)",
                pageSize=100,
                pageToken=page,
                **kw,
            )
            .execute()
        )
        for f in resp.get("files") or []:
            exist.add(str(f.get("name") or ""))
        page = resp.get("nextPageToken")
        if not page:
            break

    uploaded: list[str] = []
    skipped: list[str] = []
    for p in pdfs:
        if p.name in exist:
            skipped.append(p.name)
            continue
        mime = mimetypes.guess_type(p.name)[0] or "application/pdf"
        media = MediaFileUpload(str(p), mimetype=mime, resumable=True)
        svc.files().create(
            body={"name": p.name, "parents": [dest_id]},
            media_body=media,
            fields="id,name",
            supportsAllDrives=True,
        ).execute()
        uploaded.append(p.name)

    url = f"https://drive.google.com/drive/u/1/folders/{dest_id}"
    deals_state[deal_id] = {
        "folder_id": dest_id,
        "folder_name": dest_name,
        "url": url,
        "files": len(exist) + len(uploaded),
    }
    state.update(
        {
            "root_folder_id": root_id,
            "root_folder_name": cfg.get("root_folder_name"),
            "root_url": cfg.get("root_url"),
            "login_hint": cfg.get("login_hint"),
            "token_name": token_name,
            "deals": deals_state,
        }
    )
    save_state(state)
    return {
        "ok": True,
        "folder_id": dest_id,
        "folder_name": dest_name,
        "url": url,
        "uploaded": uploaded,
        "skipped": skipped,
    }


def update_deal_overrides(deal_id: str, url: str, folder_name: str) -> None:
    sb = sb_client()
    r = (
        sb.table("kurashift_re_deals")
        .select("summary_json")
        .eq("id", deal_id)
        .single()
        .execute()
    )
    sj = r.data.get("summary_json") if r.data else {}
    if not isinstance(sj, dict):
        sj = {}
    ov = dict(sj.get("ops_form_overrides") or {})
    ov["drive_folder"] = url
    ov["property_name"] = folder_name
    sj["ops_form_overrides"] = ov
    draft = sj.get("ops_form_draft") if isinstance(sj.get("ops_form_draft"), dict) else {}
    for item in draft.get("filled") or []:
        if not isinstance(item, dict):
            continue
        if item.get("id") == "drive_folder":
            item["value"] = url
            item["source"] = "override"
        if item.get("id") == "property_name":
            item["value"] = folder_name
            item["source"] = "override"
    if draft:
        sj["ops_form_draft"] = draft
    sb.table("kurashift_re_deals").update({"summary_json": sj}).eq("id", deal_id).execute()


def main() -> int:
    ap = argparse.ArgumentParser(description="神大家割当 Drive へ物件資料アップロード")
    ap.add_argument("--deal-id", required=True)
    ap.add_argument("--apply", action="store_true", help="実際に作成・アップロード")
    ap.add_argument(
        "--update-deal",
        action="store_true",
        help="ops_form_overrides の drive_folder / property_name を更新",
    )
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    sb = sb_client()
    r = (
        sb.table("kurashift_re_deals")
        .select("id,title,area,price_man,summary_json")
        .eq("id", args.deal_id)
        .single()
        .execute()
    )
    deal = r.data
    if not deal:
        raise SystemExit("deal が見つかりません")

    result = upload_folder(deal=deal, dry_run=not args.apply)
    if args.apply and args.update_deal and result.get("url"):
        update_deal_overrides(
            args.deal_id,
            str(result["url"]),
            str(result.get("folder_name") or ""),
        )
        result["deal_updated"] = True

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print("📎 神大家割当 Drive（運営相談・資料格納）")
        print(f"- フォルダ: {result.get('folder_name')}")
        print(f"- URL: {result.get('url') or '(dry-run)'}")
        if result.get("uploaded") is not None:
            print(f"- 追加: {len(result.get('uploaded') or [])} / 既存スキップ: {len(result.get('skipped') or [])}")
        if result.get("dry_run"):
            print(f"- 予定ファイル: {len(result.get('files') or [])}件（--apply で実行）")
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
