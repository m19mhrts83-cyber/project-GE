#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""FRIDAY 定例向け Notion 操作（REST API）。

jarvis_notion_api.py はタスクDB寄りのため、週次ページの
「子ページ検索 → ページ末尾へブロック追記 → 画像アップロード」を
このモジュールに分離する。破壊的操作（削除・移動）は持たない。

前提: .env.jarvis_private の NOTION_API_TOKEN（松野家WS / Jarvisダッシュボード）。
値は出力しない。
"""
from __future__ import annotations

import json
import mimetypes
import os
import re
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Any, Iterable

API = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"
MAX_TEXT = 1900


class NotionError(RuntimeError):
    pass


def _token() -> str:
    tok = (os.environ.get("NOTION_API_TOKEN") or os.environ.get("NOTION_TOKEN") or "").strip()
    if not tok:
        raise NotionError("NOTION_API_TOKEN 未設定（.env.jarvis_private）")
    return tok


def _headers(*, json_body: bool = True) -> dict[str, str]:
    h = {
        "Authorization": f"Bearer {_token()}",
        "Notion-Version": NOTION_VERSION,
    }
    if json_body:
        h["Content-Type"] = "application/json"
    return h


def _request(
    method: str,
    path: str,
    body: dict[str, Any] | None = None,
    *,
    raw: bytes | None = None,
    content_type: str | None = None,
    retries: int = 3,
) -> dict[str, Any]:
    url = f"{API}{path}"
    last: Exception | None = None
    for attempt in range(retries):
        try:
            if raw is not None:
                headers = _headers(json_body=False)
                if content_type:
                    headers["Content-Type"] = content_type
                data = raw
            else:
                headers = _headers()
                data = None if body is None else json.dumps(body).encode("utf-8")
            req = urllib.request.Request(url, data=data, headers=headers, method=method)
            with urllib.request.urlopen(req, timeout=60) as resp:
                payload = resp.read().decode("utf-8", "replace")
                return json.loads(payload) if payload.strip() else {}
        except urllib.error.HTTPError as e:
            err = e.read().decode("utf-8", "replace")[:500]
            last = NotionError(f"HTTP {e.code} {path}: {err}")
            if e.code in (429, 500, 502, 503, 504) and attempt + 1 < retries:
                time.sleep(1.5 * (attempt + 1))
                continue
            raise last
        except urllib.error.URLError as e:
            last = NotionError(f"{path}: {e}")
            if attempt + 1 < retries:
                time.sleep(1.5 * (attempt + 1))
                continue
            raise last
    raise last or NotionError(f"{path}: unknown error")


def normalize_page_id(raw: str) -> str:
    pid = (raw or "").replace("-", "").strip()
    if len(pid) == 32:
        return f"{pid[:8]}-{pid[8:12]}-{pid[12:16]}-{pid[16:20]}-{pid[20:]}"
    return (raw or "").strip()


def page_url(page_id: str) -> str:
    return f"https://app.notion.com/p/{page_id.replace('-', '')}"


# --------------------------------------------------------------------------
# 読み取り
# --------------------------------------------------------------------------
def list_children(block_id: str, *, max_pages: int = 20) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    cursor: str | None = None
    for _ in range(max_pages):
        q = "/blocks/%s/children?page_size=100" % normalize_page_id(block_id)
        if cursor:
            q += f"&start_cursor={cursor}"
        data = _request("GET", q)
        out.extend(data.get("results") or [])
        cursor = data.get("next_cursor")
        if not data.get("has_more") or not cursor:
            break
    return out


def plain_text(block: dict[str, Any]) -> str:
    btype = block.get("type") or ""
    payload = block.get(btype) or {}
    if not isinstance(payload, dict):
        return ""
    if btype == "child_page":
        return str(payload.get("title") or "")
    return "".join(str(x.get("plain_text") or "") for x in (payload.get("rich_text") or []))


DATED_TITLE_RE = re.compile(r"^\((\d{4})/(\d{1,2})/(\d{1,2})\)")


def find_dated_child(hub_id: str, year: int, month: int, day: int) -> dict[str, Any] | None:
    hits: list[dict[str, Any]] = []
    for b in list_children(hub_id):
        if b.get("type") != "child_page":
            continue
        title = plain_text(b)
        m = DATED_TITLE_RE.match(title.strip())
        if not m:
            continue
        if (int(m.group(1)), int(m.group(2)), int(m.group(3))) == (year, month, day):
            hits.append({"id": b["id"], "title": title.strip()})
    return hits[-1] if hits else None


def has_heading(page_id: str, prefix: str) -> bool:
    for b in list_children(page_id):
        if b.get("type") == "heading_2" and plain_text(b).strip().startswith(prefix):
            return True
    return False


# --------------------------------------------------------------------------
# ブロック生成
# --------------------------------------------------------------------------
def _split_text(text: str, limit: int = MAX_TEXT) -> list[str]:
    if len(text) <= limit:
        return [text]
    return [text[i : i + limit] for i in range(0, len(text), limit)]


def rich_text(text: str) -> list[dict[str, Any]]:
    """`**bold**` を Notion の bold に変換。長文は分割。"""
    parts = re.split(r"(\*\*.+?\*\*|__.+?__)", text)
    items: list[dict[str, Any]] = []
    for part in parts:
        if not part:
            continue
        bold = (part.startswith("**") and part.endswith("**")) or (
            part.startswith("__") and part.endswith("__")
        )
        body = part[2:-2] if bold else part
        for chunk in _split_text(body):
            if not chunk:
                continue
            item: dict[str, Any] = {"type": "text", "text": {"content": chunk}}
            if bold:
                item["annotations"] = {"bold": True}
            items.append(item)
    return items or [{"type": "text", "text": {"content": ""}}]


def _block(btype: str, text: str = "") -> dict[str, Any]:
    payload: dict[str, Any] = {"rich_text": rich_text(text)}
    return {"object": "block", "type": btype, btype: payload}


def heading_2(text: str) -> dict[str, Any]:
    return _block("heading_2", text)


def heading_3(text: str) -> dict[str, Any]:
    return _block("heading_3", text)


def heading_4(text: str) -> dict[str, Any]:
    return _block("heading_4", text)


def bullet(text: str) -> dict[str, Any]:
    return _block("bulleted_list_item", text)


def numbered(text: str) -> dict[str, Any]:
    return _block("numbered_list_item", text)


def paragraph(text: str) -> dict[str, Any]:
    return _block("paragraph", text)


def divider() -> dict[str, Any]:
    return {"object": "block", "type": "divider", "divider": {}}


def image_block(file_upload_id: str, caption: str = "") -> dict[str, Any]:
    payload: dict[str, Any] = {
        "type": "file_upload",
        "file_upload": {"id": file_upload_id},
    }
    if caption:
        payload["caption"] = rich_text(caption)
    return {"object": "block", "type": "image", "image": payload}


def md_to_blocks(md: str) -> list[dict[str, Any]]:
    """Genspark summary (Markdown) → Notion blocks."""
    blocks: list[dict[str, Any]] = []
    for raw in (md or "").splitlines():
        line = raw.rstrip()
        stripped = line.strip()
        if not stripped:
            continue
        m = re.match(r"^(#{1,6})\s+(.*)$", stripped)
        if m:
            level = len(m.group(1))
            text = m.group(2).strip()
            if level <= 2:
                blocks.append(heading_3(text))
            elif level == 3:
                blocks.append(heading_3(text))
            else:
                blocks.append(heading_4(text))
            continue
        if re.match(r"^[-*]\s+", stripped):
            blocks.append(bullet(re.sub(r"^[-*]\s+", "", stripped)))
            continue
        if re.match(r"^\d+[.)]\s+", stripped):
            blocks.append(numbered(re.sub(r"^\d+[.)]\s+", "", stripped)))
            continue
        if re.match(r"^---+$", stripped):
            blocks.append(divider())
            continue
        if stripped.startswith(">"):
            blocks.append(paragraph(stripped.lstrip("> ").strip()))
            continue
        blocks.append(paragraph(stripped))
    return blocks


# --------------------------------------------------------------------------
# 追記・アップロード
# --------------------------------------------------------------------------
def append_blocks(block_id: str, blocks: Iterable[dict[str, Any]], *, chunk: int = 50) -> int:
    items = list(blocks)
    total = 0
    for i in range(0, len(items), chunk):
        data = _request(
            "PATCH",
            f"/blocks/{normalize_page_id(block_id)}/children",
            {"children": items[i : i + chunk]},
        )
        total += len(data.get("results") or [])
        time.sleep(0.35)
    return total


def upload_file(path: Path, *, content_type: str | None = None) -> str:
    data = path.read_bytes()
    ctype = content_type or mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    created = _request(
        "POST",
        "/file_uploads",
        {
            "mode": "single_part",
            "filename": path.name,
            "content_type": ctype,
        },
    )
    upload_id = created.get("id")
    if not upload_id:
        raise NotionError(f"file_upload id が返りません: {created}")

    boundary = "----FRIDAY" + uuid.uuid4().hex
    filename = path.name.replace('"', "_")
    body = b"".join(
        [
            f"--{boundary}\r\n".encode(),
            f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'.encode(),
            f"Content-Type: {ctype}\r\n\r\n".encode(),
            data,
            f"\r\n--{boundary}--\r\n".encode(),
        ]
    )
    sent = _request(
        "POST",
        f"/file_uploads/{upload_id}/send",
        raw=body,
        content_type=f"multipart/form-data; boundary={boundary}",
    )
    if sent.get("status") not in (None, "uploaded", "pending"):
        raise NotionError(f"file_upload send status={sent.get('status')}")
    return upload_id
