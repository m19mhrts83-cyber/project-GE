#!/usr/bin/env python3
"""
CHRLINE メッセージの画像・動画・音声・ファイルを
パートナーフォルダの 1.受信添付(Stock)/YYYY-MM-DD/ へ保存する（ベストエフォート）。

公式エクスポートやスタンプは対象外。失敗時はログのみで本文プレースホルダは残す。
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

from CHRLINE.helpers.bulders.message import Message as BuilderMessage
from CHRLINE.helpers.bulders.message import MediaMessage
from CHRLINE.serializers.DummyProtocol import DummyThrift

from chrline_dump_messages_poc import _msg_content_type
from chrline_sync_delta_poc import (
    _normalize_content_metadata_for_decrypt,
    _wrap_message_for_e2ee_decrypt,
)

# contentType: IMAGE=1 VIDEO=2 AUDIO=3 FILE=14
_MEDIA_CONTENT_TYPES = frozenset({1, 2, 3, 14})
_CT_LABEL = {1: "image", 2: "video", 3: "audio", 14: "file"}
_CT_EXT = {1: ".jpg", 2: ".mp4", 3: ".m4a", 14: ".bin"}

_YORITOORI_MANUAL = (
    Path.home()
    / "git-repos"
    / "215_kamiooya"
    / "C1_cursor"
    / "1b_Cursorマニュアル"
)


def _ensure_yoritoori_utils():
    if str(_YORITOORI_MANUAL) not in sys.path:
        sys.path.insert(0, str(_YORITOORI_MANUAL))
    from yoritoori_utils import (  # noqa: WPS433
        parse_received_date_folder,
        resolve_incoming_attach_date_dir,
    )

    return parse_received_date_folder, resolve_incoming_attach_date_dir


def sanitize_filename(name: str) -> str:
    s = re.sub(r'[<>:"/\\|?*]', "_", name or "")
    s = re.sub(r"\s+", "_", s.strip())
    return s or "attachment"


def ensure_incoming_stock_dir(partner_folder: Path) -> Path:
    partner_folder = Path(partner_folder)
    stock = partner_folder / "1.受信添付(Stock)"
    if not stock.exists():
        alt = partner_folder / "添付"
        if not (alt.exists() and alt.is_dir()):
            stock.mkdir(parents=True, exist_ok=True)
    return stock


def _content_metadata_dict(cl, msg) -> dict[str, str]:
    md = cl.checkAndGetValue(msg, "contentMetadata", 18)
    if md is None and isinstance(msg, dict):
        md = msg.get(18) or msg.get("contentMetadata")
    if not md:
        return {}
    out: dict[str, str] = {}
    try:
        items = md.items() if isinstance(md, dict) else None
        if items is None and hasattr(md, "dd"):
            items = md.dd().items()
        if not items:
            return {}
        for k, v in items:
            if v is None:
                continue
            sk = k.decode("utf-8", errors="replace") if isinstance(k, bytes) else str(k)
            if isinstance(v, (bytes, bytearray)):
                sv = v.decode("utf-8", errors="replace")
            else:
                sv = str(v)
            out[sk] = sv
    except Exception:
        return {}
    return out


def _guess_filename(cl, msg, ct: int) -> str:
    meta = _content_metadata_dict(cl, msg)
    for key in ("FILE_NAME", "filename", "name", "NAME"):
        if meta.get(key):
            return sanitize_filename(meta[key])
    mid = ""
    try:
        mid = str(cl.checkAndGetValue(msg, "id", 4) or "")
    except Exception:
        mid = ""
    kind = _CT_LABEL.get(ct, "media")
    ext = _CT_EXT.get(ct, ".bin")
    raw_info = meta.get("MEDIA_CONTENT_INFO") or ""
    if raw_info:
        try:
            import json

            info = json.loads(raw_info)
            e = str(info.get("extension") or "").strip().lstrip(".")
            if e:
                ext = f".{e}"
        except Exception:
            pass
    if ct == 14:
        for key in ("EXTENSION", "ext"):
            e = (meta.get(key) or "").strip().lstrip(".")
            if e:
                ext = f".{e}"
                break
    base = f"{kind}_{mid}" if mid else kind
    if base.lower().endswith(ext.lower()):
        return sanitize_filename(base)
    return sanitize_filename(base) + ext


def is_downloadable_media(cl, msg) -> bool:
    ct = _msg_content_type(cl, msg)
    return ct in _MEDIA_CONTENT_TYPES


def _infer_to_type(cl, msg) -> int | None:
    """メッセージの to / chat mid から toType を推定。"""
    to = None
    try:
        to = cl.checkAndGetValue(msg, "to", 2)
    except Exception:
        to = None
    if to is None and isinstance(msg, dict):
        to = msg.get(2) or msg.get("to")
    if to is None:
        try:
            to = getattr(msg, "val_2", None)
        except Exception:
            to = None
    s = str(to or "").strip()
    if s.startswith("u"):
        return 0  # USER
    if s.startswith("c"):
        return 2  # GROUP
    if s.startswith("r"):
        return 1  # ROOM
    if s.startswith("m"):
        return 4  # SQUARE_CHAT 系
    return None


def _ensure_media_message(cl, msg, op) -> MediaMessage | None:
    """MediaMessage にラップし、E2EE download 用の _ref を付ける。"""
    _normalize_content_metadata_for_decrypt(cl, msg)

    wrapped: object | None = None
    # getRecentMessagesV2 等は既に MediaMessage のことが多い → 再ラップでフィールド欠落しやすい
    if isinstance(msg, MediaMessage):
        wrapped = msg
    elif op is not None:
        wrapped = _wrap_message_for_e2ee_decrypt(cl, op, msg)

    if not isinstance(wrapped, MediaMessage):
        try:
            dd = msg.dd() if hasattr(msg, "dd") else {}
            if isinstance(msg, dict):
                ins_map = {
                    int(k): v
                    for k, v in msg.items()
                    if str(k).isdigit() or isinstance(k, int)
                }
            else:
                ins_map = {int(k): v for k, v in (dd or {}).items()}
            ct = _msg_content_type(cl, msg)
            if ct is not None and 15 not in ins_map:
                ins_map[15] = ct
            if 3 not in ins_map or ins_map.get(3) is None:
                inferred = _infer_to_type(cl, msg)
                if inferred is not None:
                    ins_map[3] = inferred
            if 4 not in ins_map or ins_map.get(4) in (None, ""):
                mid = None
                try:
                    mid = cl.checkAndGetValue(msg, "id", 4)
                except Exception:
                    mid = None
                if mid is None and isinstance(msg, dict):
                    mid = msg.get(4) or msg.get("id")
                if mid is None:
                    mid = getattr(msg, "val_4", None)
                if mid is not None:
                    ins_map[4] = mid
            if 18 not in ins_map or not ins_map.get(18):
                meta = _content_metadata_dict(cl, msg)
                if meta:
                    ins_map[18] = meta
            if 20 not in ins_map:
                chunks = None
                try:
                    chunks = cl.checkAndGetValue(msg, "chunks", 20)
                except Exception:
                    chunks = None
                if chunks is None and isinstance(msg, dict):
                    chunks = msg.get(20) or msg.get("chunks")
                if chunks is None:
                    chunks = getattr(msg, "val_20", None)
                if chunks is not None:
                    ins_map[20] = chunks
            wrapped = BuilderMessage(ins=ins_map, cl=cl)
        except Exception:
            return None

    if not isinstance(wrapped, MediaMessage):
        return None

    try:
        if wrapped[3] is None:
            inferred = _infer_to_type(cl, msg)
            if inferred is not None:
                wrapped[3] = inferred
    except Exception:
        pass

    need_ref = True
    try:
        ref = getattr(wrapped, "_ref", None)
        if isinstance(ref, DummyThrift):
            need_ref = False
    except Exception:
        need_ref = True
    if need_ref:
        if op is not None and isinstance(op, DummyThrift):
            try:
                wrapped.set_ref(op)
            except Exception:
                pass
        else:
            fake = DummyThrift(name="Operation", cl=cl)
            try:
                fake[3] = 26
            except Exception:
                setattr(fake, "val_3", 26)
            try:
                wrapped.set_ref(fake)
            except Exception:
                pass
    return wrapped


def try_save_line_media(
    cl,
    msg,
    op,
    yoritoori_md: Path,
    date_str: str,
    *,
    dry_run: bool = False,
) -> list[str]:
    """
    メディア contentType なら download → Stock 保存。
    成功時は ["YYYY-MM-DD/保存名"]。失敗・非対象は []。
    """
    ct = _msg_content_type(cl, msg)
    if ct not in _MEDIA_CONTENT_TYPES:
        return []

    partner_dir = Path(yoritoori_md).resolve().parent
    parse_received_date_folder, resolve_incoming_attach_date_dir = _ensure_yoritoori_utils()

    try:
        wrapped = _ensure_media_message(cl, msg, op)
        if wrapped is None:
            print(
                f"# LINE添付: MediaMessage 化できず contentType={ct} → スキップ",
                file=sys.stderr,
            )
            return []

        data = wrapped.download(savePath=None)
        if not data:
            print(f"# LINE添付: download 結果が空 contentType={ct}", file=sys.stderr)
            return []
        if isinstance(data, str):
            data = data.encode("utf-8", errors="replace")
        if not isinstance(data, (bytes, bytearray)):
            print(
                f"# LINE添付: 予期しない download 型 {type(data).__name__}",
                file=sys.stderr,
            )
            return []
        buf = bytes(data)
    except Exception as e:
        print(
            f"# LINE添付取得失敗 contentType={ct}: {type(e).__name__}: {e}",
            file=sys.stderr,
        )
        return []

    if dry_run:
        print(
            f"[dry-run] LINE添付保存予定 → {partner_dir.name} ({len(buf)} bytes)",
            file=sys.stderr,
        )
        return []

    ensure_incoming_stock_dir(partner_dir)
    attach_dir = resolve_incoming_attach_date_dir(partner_dir, date_str)
    date_folder = parse_received_date_folder(date_str)
    date_prefix = date_str.replace("/", "").replace(" ", "_")
    safe = _guess_filename(cl, msg, ct)
    dest_path = attach_dir / f"{date_prefix}_{safe}"

    counter = 0
    while dest_path.exists():
        try:
            if dest_path.stat().st_size == len(buf):
                break
        except OSError:
            pass
        counter += 1
        dest_path = attach_dir / f"{dest_path.stem}_{counter}{dest_path.suffix}"

    if not dest_path.exists() or dest_path.stat().st_size != len(buf):
        dest_path.write_bytes(buf)

    rel = f"{date_folder}/{dest_path.name}"
    print(f"  LINE添付保存: {partner_dir.name}/1.受信添付(Stock)/{rel}", file=sys.stderr)
    return [rel]


def attach_md_block(attachment_names: list[str] | None) -> str:
    if not attachment_names:
        return ""
    return (
        "\n**添付ファイル**: "
        + ", ".join(attachment_names)
        + "（添付フォルダに保存）\n"
    )
