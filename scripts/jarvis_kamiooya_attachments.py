#!/usr/bin/env python3
"""既存WeStudyアーカイブ→private Storageとコメント子表。既定はdry-run。

SUPABASE_URL/SUPABASE_SERVICE_ROLE_KEYは神大家用のみ。認証・署名URL・本文・
ローカルパスをDBや出力へ含めない。元アーカイブを変更・削除しない。
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import re
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import requests

PROJECT_URL = "https://mwubzgefkkjjbingrmqu.supabase.co"
BUCKET = "community-attachments"
MAX_BYTES = 50 * 1024 * 1024
ARCHIVE = Path.home() / "Library/CloudStorage/GoogleDrive-admin@livingsupport-matsu.co.jp/マイドライブ/215_神大家_WeStudyスクレイプ/runs"
_UNSET = object()


def normalize_comment_id(raw: str) -> str:
    value = re.sub(r"^comment-", "", str(raw).strip())
    if not re.fullmatch(r"[0-9]+", value):
        raise ValueError("invalid_comment_id")
    return value


def canonical_url(raw: str) -> str:
    u = urlsplit(raw)
    if u.scheme not in ("http", "https") or u.username or u.password or not u.hostname:
        raise ValueError("invalid_source_url")
    # 一時トークン・追跡情報は保存しない。取得済みファイルの識別にのみ使用。
    # 旧HTTPの資料URLも識別子として保持する。ここからネット取得は行わない。
    return urlunsplit((u.scheme, u.netloc.lower(), u.path, "", ""))


def inspect_file(path: Path, root: Path) -> tuple[bytes, str, str]:
    resolved = path.resolve()
    if not resolved.is_relative_to(root.resolve()) or not resolved.is_file():
        raise ValueError("file_outside_archive_or_missing")
    if not 0 < resolved.stat().st_size <= MAX_BYTES:
        raise ValueError("file_size_limit")
    data = resolved.read_bytes()
    if not 0 < len(data) <= MAX_BYTES:
        raise ValueError("file_size_limit")
    ext = resolved.suffix.lower()
    if ext in (".jpg", ".jpeg") and data.startswith(b"\xff\xd8\xff"):
        return data, "image/jpeg", ".jpg"
    if ext == ".png" and data.startswith(b"\x89PNG\r\n\x1a\n"):
        return data, "image/png", ".png"
    if ext == ".pdf" and data.startswith(b"%PDF-"):
        return data, "application/pdf", ".pdf"
    if ext in (".xlsx", ".docx", ".pptx", ".zip") and data.startswith(b"PK"):
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            names = set(z.namelist())
            office = {".xlsx": ("xl/workbook.xml", "spreadsheetml.sheet"), ".docx": ("word/document.xml", "wordprocessingml.document"), ".pptx": ("ppt/presentation.xml", "presentationml.presentation")}
            if ext in office and "[Content_Types].xml" in names and office[ext][0] in names:
                return data, "application/vnd.openxmlformats-officedocument." + office[ext][1], ext
            if ext == ".zip":
                return data, "application/zip", ext
    if ext == ".webp" and data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return data, "image/webp", ext
    if ext == ".heic" and data[4:8] == b"ftyp" and data[8:12] in (b"heic", b"heix", b"mif1"):
        return data, "image/heic", ext
    if ext == ".doc" and data.startswith(bytes.fromhex("d0cf11e0a1b11ae1")):
        return data, "application/msword", ext
    if ext == ".csv":
        for encoding in ("utf-8-sig", "cp932"):
            try:
                text = data.decode(encoding)
                if "\x00" not in text and not re.search(r"<\s*(?:!doctype|html|script)\b", text, re.I) and ("," in text or "\t" in text):
                    return data, "text/csv", ext
            except UnicodeDecodeError:
                pass
    raise ValueError("unsupported_or_invalid_file")


def build_attachment(row: dict, root: Path = ARCHIVE) -> tuple[dict, bytes]:
    cid = normalize_comment_id(row.get("comment_id", ""))
    url = canonical_url(row.get("url", ""))
    path = Path(row.get("local_path", ""))
    data, mime, ext = inspect_file(path, root)
    digest = hashlib.sha256(data).hexdigest()
    identity = hashlib.sha256(f"{cid}\0{url}".encode()).hexdigest()
    return {
        "id": identity, "comment_id": cid, "bucket": BUCKET,
        "storage_path": f"comments/{cid}/{digest}{ext}",
        "source_url": url, "original_name": Path(str(row.get("name") or path.name)).name[:255],
        "content_type": mime, "byte_size": len(data), "sha256": digest,
    }, data


class Store:
    def __init__(self):
        if os.environ.get("SUPABASE_URL", "").rstrip("/") != PROJECT_URL:
            raise ValueError("wrong_supabase_project")
        key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
        if not key:
            raise ValueError("service_key_required")
        self.session = requests.Session()
        self.session.headers.update({"apikey": key, "Authorization": f"Bearer {key}"})

    def request(self, method: str, path: str, **kwargs):
        r = self.session.request(method, PROJECT_URL + path, timeout=60, **kwargs)
        if not r.ok:
            # 応答本文はURL・認証情報等を含み得るため出力しない。
            raise RuntimeError(f"supabase_http_{r.status_code}")
        return r

    def ensure_bucket(self):
        buckets = self.request("GET", "/storage/v1/bucket").json()
        existing = next((b for b in buckets if b["id"] == BUCKET), None)
        if existing:
            if existing.get("public"):
                raise ValueError("bucket_must_be_private")
            if existing.get("file_size_limit") is not None and existing["file_size_limit"] < MAX_BYTES:
                self.request("PUT", "/storage/v1/bucket/" + BUCKET, json={"public": False, "file_size_limit": MAX_BYTES})
            return
        self.request("POST", "/storage/v1/bucket", json={
            "id": BUCKET, "name": BUCKET, "public": False, "file_size_limit": MAX_BYTES,
        })

    def exists_comment(self, cid: str) -> bool:
        rows = self.request("GET", "/rest/v1/comments", params={
            "select": "comment_id", "comment_id": f"eq.{cid}", "limit": 1,
        }).json()
        return len(rows) == 1

    def existing(self, ident: str):
        rows = self.request("GET", "/rest/v1/community_attachments", params={
            "select": "id,sha256,storage_path,original_name", "id": f"eq.{ident}", "limit": 1,
        }).json()
        return rows[0] if rows else None

    def save(self, meta: dict, data: bytes, old_record=_UNSET, publish=True) -> str:
        old = self.existing(meta["id"]) if old_record is _UNSET else old_record
        path = f"/storage/v1/object/{BUCKET}/{meta['storage_path']}"
        if old and old["sha256"] == meta["sha256"] and old["storage_path"] == meta["storage_path"]:
            # DBだけ成功とせず、実体の欠落・破損も検出する。
            body = self.request("GET", path).content
            if hashlib.sha256(body).hexdigest() != meta["sha256"]:
                raise ValueError("stored_hash_mismatch")
            if publish and meta.get("original_name") and old.get("original_name") != meta["original_name"]:
                self.request("PATCH", "/rest/v1/community_attachments", params={"id": "eq." + meta["id"]}, json={"original_name": meta["original_name"], "updated_at": datetime.now(timezone.utc).isoformat()})
            return "unchanged"
        # 内容ハッシュをキーにするため異なる内容を上書きしない。
        self.request("POST", path, data=data, headers={"Content-Type": meta["content_type"], "x-upsert": "true"})
        body = self.request("GET", path).content
        if hashlib.sha256(body).hexdigest() != meta["sha256"]:
            raise ValueError("stored_hash_mismatch")
        if publish:
            self.request("POST", "/rest/v1/community_attachments", params={"on_conflict": "id"},
                         json={**meta, "updated_at": datetime.now(timezone.utc).isoformat()},
                         headers={"Prefer": "resolution=merge-duplicates,return=minimal"})
        return "saved"


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--catalog", type=Path, action="append", required=True)
    p.add_argument("--comment-id", action="append", default=[])
    p.add_argument("--content-type", action="append", default=[])
    p.add_argument("--limit", type=int, default=3)
    p.add_argument("--apply", action="store_true")
    p.add_argument("--report", type=Path, required=True)
    args = p.parse_args(argv)
    if not 1 <= args.limit <= 100:
        p.error("limit must be 1..100")
    wanted = {normalize_comment_id(x) for x in args.comment_id}
    store = Store()
    counts = {"saved": 0, "unchanged": 0, "dry_run": 0, "invalid": 0, "missing_comment": 0, "failed": 0}
    records = []
    seen = set()
    for catalog in args.catalog:
        if not catalog.resolve().is_relative_to(ARCHIVE.resolve()):
            raise ValueError("catalog_outside_archive")
        for line in catalog.read_text(encoding="utf-8").splitlines():
            try:
                row = json.loads(line)
                if wanted and normalize_comment_id(row.get("comment_id", "")) not in wanted:
                    continue
                meta, data = build_attachment(row)
                if args.content_type and meta["content_type"] not in args.content_type:
                    continue
            except (ValueError, OSError, zipfile.BadZipFile):
                counts["invalid"] += 1
                continue
            if meta["id"] in seen:
                continue
            seen.add(meta["id"])
            if len(records) >= args.limit:
                break
            try:
                if not store.exists_comment(meta["comment_id"]):
                    counts["missing_comment"] += 1
                    continue
                if args.apply:
                    store.ensure_bucket()
                    status = store.save(meta, data)
                else:
                    status = "dry_run"
                counts[status] += 1
                records.append({k: meta[k] for k in ("id", "comment_id", "storage_path", "content_type", "byte_size", "sha256")} | {"result": status})
            except (ValueError, RuntimeError, requests.RequestException) as exc:
                counts["failed"] += 1
                records.append({"id": meta["id"], "result": "failed", "error": type(exc).__name__})
        if len(records) >= args.limit:
            break
    report = {"at": datetime.now(timezone.utc).isoformat(), "apply": args.apply, "counts": counts, "records": records}
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"apply": args.apply, **counts, "selected": len(records)}))
    return 1 if counts["failed"] or not records else 0


if __name__ == "__main__":
    raise SystemExit(main())
