#!/usr/bin/env python3
"""懇親会開催申込書.docx をイベント情報で更新し、神大家割当 Google Drive にアップロードする。"""

from __future__ import annotations

import argparse
import re
import shutil
import sys
import zipfile
from datetime import date
from io import BytesIO
from pathlib import Path
from xml.etree import ElementTree as ET

from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

from google_workspace_auth import CREDENTIALS_PATH, load_credentials

MANUAL_DIR = CREDENTIALS_PATH.parent

# 神大家割当フォルダは共有ドライブ内（supportsAllDrives 必須）
DRIVE_SHARED_KWARGS = {
    "supportsAllDrives": True,
    "includeItemsFromAllDrives": True,
}

W_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"

DEFAULT_DOCX = Path(
    "/Users/matsunomasaharu2/Library/CloudStorage/OneDrive-個人用/215_神・大家さん倶楽部"
    "/01_運営サポート/飲み会幹事/懇親会開催申込書.docx"
)

# w:t ノード index（0始まり）→ 新テキスト。テンプレ docx の分割構造に依存。
EVENTS: dict[str, dict] = {
    "2026-08-gifu": {
        "drive_folder_id": "1L5PM4T5AAkD5a3zWzXY_ypW38v0qhdlh",
        "drive_folder_url": "https://drive.google.com/drive/u/2/folders/1L5PM4T5AAkD5a3zWzXY_ypW38v0qhdlh",
        "drive_login_hint": "matsuno.estate@gmail.com",
        "drive_token_name": "token_google_workspace_estate.json",
        "drive_filename": "懇親会開催申込書.docx",
        "node_replacements": {
            11: "6",    # 記入月
            13: "25",   # 記入日
            23: "8",    # 開催月
            25: "29",   # 開催日
            30: "17",   # 開始時
            32: "00",   # 開始分
            36: "岐阜県",
            38: "岐阜駅周辺",
            42: "夕涼みの会 in 岐阜",
            43: "東海北陸エリアメンバー",
            44: "40",   # 2025夏in岐阜実績ベース
            48: "17",
            50: "00",
            51: "分、ルベッタ岐阜駅玉宮店に集合、",
            52: "1",
            53: "9",
            54: "時",
            55: "30",
            56: "分頃１次会終了、",
            57: "",
            58: "２次会は天串岐阜駅前店（",
            59: "19時30分〜）を予定して実施",
            61: "□",
            64: "◼人数が多いため、運営に依頼してチケットサービスを使いたい",
        },
    },
}


def _read_docx_plain_text(docx_path: Path) -> str:
    with zipfile.ZipFile(docx_path) as zin:
        root = ET.fromstring(zin.read("word/document.xml"))
    return "".join(
        t.text or ""
        for t in root.iter(f"{W_NS}t")
    )


def _guess_archive_slug(docx_path: Path) -> str:
    """更新前ファイルからアーカイブ名を推測（目的・開催日など）。"""
    text = _read_docx_plain_text(docx_path)
    purpose = ""
    m = re.search(r"目的(.{0,20}?)対象者", text)
    if m:
        purpose = m.group(1).strip()
    purpose = re.sub(r"[^\w\u3040-\u30ff\u4e00-\u9fff]+", "", purpose)[:24] or "申込書"
    ymd = ""
    m2 = re.search(r"開催日時(\d{4})年\s*(\d{1,2})月\s*(\d{1,2})日", text)
    if m2:
        y, mo, d = m2.groups()
        ymd = f"{y}{int(mo):02d}{int(d):02d}"
    if ymd:
        return f"{ymd}_{purpose}"
    return f"{date.today().strftime('%Y%m%d')}_{purpose}"


def archive_docx_before_update(
    docx_path: Path,
    *,
    archive_dir: Path | None = None,
    archive_slug: str | None = None,
) -> Path | None:
    """更新前の docx をアーカイブフォルダへコピー（上書き更新の代わりに履歴を残す）。"""
    if not docx_path.is_file():
        return None
    archive_dir = archive_dir or (docx_path.parent / "申込書アーカイブ")
    archive_dir.mkdir(parents=True, exist_ok=True)
    slug = archive_slug or _guess_archive_slug(docx_path)
    dest = archive_dir / f"懇親会開催申込書_{slug}.docx"
    if dest.exists():
        stem = dest.stem
        n = 2
        while dest.exists():
            dest = archive_dir / f"{stem}_{n}.docx"
            n += 1
    shutil.copy2(docx_path, dest)
    return dest


def _apply_node_replacements(docx_path: Path, node_replacements: dict[int, str]) -> None:
    with zipfile.ZipFile(docx_path, "r") as zin:
        names = zin.namelist()
        files = {name: zin.read(name) for name in names}

    root = ET.fromstring(files["word/document.xml"])
    nodes = [n for n in root.iter(f"{W_NS}t") if n.text is not None]
    for idx, new_text in node_replacements.items():
        if idx < 0 or idx >= len(nodes):
            raise IndexError(f"w:t index {idx} out of range (0..{len(nodes)-1})")
        nodes[idx].text = new_text

    files["word/document.xml"] = ET.tostring(root, encoding="utf-8", xml_declaration=True)

    buf = BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zout:
        for name in names:
            zout.writestr(name, files[name])
    docx_path.write_bytes(buf.getvalue())


def _find_file_in_folder(service, folder_id: str, filename: str) -> str | None:
    q = f"name = '{filename}' and '{folder_id}' in parents and trashed = false"
    resp = (
        service.files()
        .list(
            q=q,
            spaces="drive",
            fields="files(id,name)",
            pageSize=10,
            **DRIVE_SHARED_KWARGS,
        )
        .execute()
    )
    files = resp.get("files") or []
    return files[0]["id"] if files else None


def upload_to_drive(
    local_path: Path,
    *,
    folder_id: str,
    filename: str,
    login_hint: str | None = None,
    token_name: str | None = None,
) -> dict:
    token_path = MANUAL_DIR / token_name if token_name else None
    creds = load_credentials(login_hint=login_hint, token_path=token_path)
    service = build("drive", "v3", credentials=creds, cache_discovery=False)
    media = MediaFileUpload(
        str(local_path),
        mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )

    existing_id = _find_file_in_folder(service, folder_id, filename)
    if existing_id:
        try:
            result = (
                service.files()
                .update(
                    fileId=existing_id,
                    media_body=media,
                    fields="id,name,webViewLink",
                    supportsAllDrives=True,
                )
                .execute()
            )
            return {"action": "updated", **result}
        except Exception as exc:
            # drive.file スコープでは既存ファイルの上書き不可のことがある → 新規作成
            err = str(exc)
            if "appNotAuthorizedToFile" not in err and "403" not in err:
                raise
            alt_name = filename.replace(".docx", "_更新.docx")
            metadata = {"name": alt_name, "parents": [folder_id]}
            result = (
                service.files()
                .create(
                    body=metadata,
                    media_body=media,
                    fields="id,name,webViewLink",
                    supportsAllDrives=True,
                )
                .execute()
            )
            return {"action": "created_fallback", "note": "既存ファイルは上書き不可のため別名で作成", **result}

    metadata = {"name": filename, "parents": [folder_id]}
    result = (
        service.files()
        .create(
            body=metadata,
            media_body=media,
            fields="id,name,webViewLink",
            supportsAllDrives=True,
        )
        .execute()
    )
    return {"action": "created", **result}


def main() -> int:
    parser = argparse.ArgumentParser(description="懇親会開催申込書を更新して Google Drive に配置")
    parser.add_argument("--event-id", default="2026-08-gifu", choices=sorted(EVENTS))
    parser.add_argument("--docx", type=Path, default=DEFAULT_DOCX)
    parser.add_argument("--dry-run", action="store_true", help="Drive アップロードせずローカル更新のみ")
    parser.add_argument("--login-hint", default="matsuno.estate@gmail.com")
    parser.add_argument("--skip-archive", action="store_true", help="更新前のアーカイブをスキップ")
    args = parser.parse_args()

    cfg = EVENTS[args.event_id]
    docx = args.docx
    if not docx.is_file():
        print(f"❌ 申込書が見つかりません: {docx}", file=sys.stderr)
        return 1

    if not args.skip_archive:
        archived = archive_docx_before_update(docx)
        if archived:
            print(f"📎 アーカイブ保存: {archived}")

    _apply_node_replacements(docx, cfg["node_replacements"])
    print(f"✅ 申込書を更新: {docx}")

    if args.dry_run:
        print("dry-run: Drive アップロードをスキップ")
        return 0

    folder_id = str(cfg["drive_folder_id"])
    filename = str(cfg["drive_filename"])
    info = upload_to_drive(
        docx,
        folder_id=folder_id,
        filename=filename,
        login_hint=str(cfg.get("drive_login_hint") or args.login_hint),
        token_name=str(cfg.get("drive_token_name") or "") or None,
    )
    print(
        f"✅ Drive {info['action']}: {info.get('name')} "
        f"https://drive.google.com/file/d/{info['id']}/view"
    )
    print(f"📁 フォルダ: https://drive.google.com/drive/folders/{folder_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
