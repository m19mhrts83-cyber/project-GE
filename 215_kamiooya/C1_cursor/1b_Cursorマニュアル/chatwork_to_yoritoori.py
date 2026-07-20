#!/usr/bin/env python3
"""
Chatwork API からメッセージを取得し、連絡先一覧.yaml の設定に従って
該当フォルダの 5.やり取り.md に追記する。

添付（[download:file_id]）は 1.受信添付(Stock)/YYYY-MM-DD/ に保存し、
やり取り.md に **添付ファイル** 行を付ける（Gmail 取り込みと同様）。

前提:
  - CHATWORK_API_TOKEN を環境変数または .env に設定
  - 連絡先一覧.yaml に chatwork_room_id を設定
  - pip install -r requirements_gmail.txt 済み（requests / PyYAML を使用）

使い方:
  python chatwork_to_yoritoori.py
  python chatwork_to_yoritoori.py --partner 神大家AI推進
  python chatwork_to_yoritoori.py --list-rooms   # room_id 確認用（トークン設定後に実行）
  python chatwork_to_yoritoori.py --rewrite-existing 306_神大家AI推進   # 既存のChatworkブロックをトグル化
  python chatwork_to_yoritoori.py --backfill-attachments --partner 神大家AI推進
"""

import argparse
import copy
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import requests
import yaml

from yoritoori_utils import (
    YORITOORI_FILENAME,
    default_yoritoori_base_dir,
    make_summary,
    mirror_yoritoori_md_to_gitrepos,
    parse_received_date_folder,
    resolve_incoming_attach_date_dir,
)

JST = ZoneInfo("Asia/Tokyo")

SCRIPT_DIR = Path(__file__).resolve().parent
BASE_DIR = default_yoritoori_base_dir()
CONTACT_YAML = BASE_DIR / "000_共通" / "連絡先一覧.yaml"
DEFAULT_PROCESSED_JSON = Path.home() / ".cursor" / "chatwork_processed.json"


def _load_env_from(path):
    """指定パスの .env を読み、os.environ に反映する。"""
    if not path.exists():
        return
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return
    for line in text.splitlines():
        m = re.match(r'^\s*([^#=]+)\s*=\s*(.+?)\s*$', line)
        if not m:
            continue
        key = m.group(1).strip()
        val = m.group(2).strip().strip("\"'")
        if val:
            os.environ[key] = val


def load_env():
    # 1) スクリプトと同じフォルダの .env
    _load_env_from(SCRIPT_DIR / ".env")
    # 2) 実行時のカレントディレクトリの .env（上書き。別ワークスペースから実行したときも拾う）
    cwd = os.getcwd()
    if cwd:
        _load_env_from(Path(cwd) / ".env")


load_env()

CHATWORK_API_TOKEN = os.environ.get("CHATWORK_API_TOKEN", "").strip()
CHATWORK_API_BASE = os.environ.get("CHATWORK_API_BASE", "https://api.chatwork.com/v2").rstrip("/")
CONTACT_PATH = Path(os.environ.get("CONTACT_LIST_PATH", CONTACT_YAML))
BASE_PATH = Path(os.environ.get("YORITOORI_BASE_PATH", BASE_DIR))
PROCESSED_JSON = Path(os.environ.get("CHATWORK_PROCESSED_PATH", DEFAULT_PROCESSED_JSON))


def load_processed():
    if not PROCESSED_JSON.exists():
        return {"rooms": {}}
    try:
        data = json.loads(PROCESSED_JSON.read_text(encoding="utf-8"))
        if isinstance(data, dict) and isinstance(data.get("rooms"), dict):
            return data
    except (json.JSONDecodeError, OSError):
        pass
    return {"rooms": {}}


def save_processed(data):
    PROCESSED_JSON.parent.mkdir(parents=True, exist_ok=True)
    PROCESSED_JSON.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


DOWNLOAD_TAG_RE = re.compile(
    r"\[download:(\d+)\]([^\[]*?)\[/download\]",
    re.IGNORECASE | re.DOTALL,
)
SIZE_SUFFIX_RE = re.compile(r"\s*\([\d.]+\s*[KMG]?B\)\s*$", re.IGNORECASE)


def sanitize_filename(name: str) -> str:
    s = re.sub(r'[<>:"/\\|?*]', "_", name or "")
    s = re.sub(r"\s+", "_", s.strip())
    return s or "attachment"


def _display_name_from_download_inner(inner: str) -> str:
    """[download] 内テキストからサイズ表記を除きファイル名にする。"""
    name = SIZE_SUFFIX_RE.sub("", (inner or "").strip()).strip()
    return name or "attachment"


def extract_chatwork_downloads(body: str) -> list[tuple[str, str]]:
    """本文から (file_id, display_name) を抽出（出現順・重複 file_id は初回のみ）。"""
    if not body:
        return []
    seen: set[str] = set()
    out: list[tuple[str, str]] = []
    for m in DOWNLOAD_TAG_RE.finditer(str(body)):
        file_id = m.group(1).strip()
        if not file_id or file_id in seen:
            continue
        seen.add(file_id)
        out.append((file_id, _display_name_from_download_inner(m.group(2))))
    return out


def ensure_incoming_stock_dir(partner_folder: Path) -> Path:
    """
    受信添付の正本フォルダ 1.受信添付(Stock) を用意する。
    resolve_incoming_attach_dir は未作成時に「添付」へ落ちるため、先に Stock を作る。
    """
    partner_folder = Path(partner_folder)
    stock = partner_folder / "1.受信添付(Stock)"
    if not stock.exists():
        alt = partner_folder / "添付"
        if not (alt.exists() and alt.is_dir()):
            stock.mkdir(parents=True, exist_ok=True)
    return stock


def clean_chatwork_body(body):
    """Chatwork の本文タグを最小限除去して読みやすくする。"""
    if not body:
        return ""
    text = str(body)
    # 宛先・返信マーカーなどを除去
    text = re.sub(r"\[To:\d+\][^\n]*\n?", "", text)
    text = re.sub(r"\[rp\s+[^\]]+\]\n?", "", text)
    # ブロックタグを除去
    text = re.sub(r"\[/?(?:info|code|qt|title)\]", "", text)
    text = re.sub(r"\[hr\]", "\n---\n", text)
    # アイコンタグを除去
    text = re.sub(r"\[piconname:[^\]]+\]", "", text)
    # ファイルアップロード周り: プレビュー・dtext を除去し、download は表示名のみ残す
    text = re.sub(r"\[dtext:file_uploaded\]", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\[preview\s+[^\]]*\]", "", text, flags=re.IGNORECASE)
    text = DOWNLOAD_TAG_RE.sub(
        lambda m: _display_name_from_download_inner(m.group(2)),
        text,
    )
    # 空行整理
    text = text.replace("\r\n", "\n")
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def format_date_jst(send_time):
    try:
        ts = int(send_time)
        dt = datetime.fromtimestamp(ts, tz=JST)
    except (TypeError, ValueError, OSError):
        dt = datetime.now(JST)
    return dt.strftime("%Y/%m/%d %H:%M")


def _flatten_notion_headings(body):
    """
    Notionミーティングメモなどで付く行頭の # / ## / ### を見出しにしないよう太字に置き換える。
    議事録の項目が一個一個畳まれないようにする。
    """
    if not body:
        return ""
    lines = body.split("\n")
    out = []
    for line in lines:
        # 行頭の ### 見出し を **見出し** に（日付パターン ### 2026/01/15 はそのまま）
        if re.match(r"^### \d{4}/\d{2}/\d{2}", line):
            out.append(line)
        elif re.match(r"^### +", line):
            rest = re.sub(r"^### +\s*", "", line)
            out.append(f"**{rest}**" if rest else line)
        elif re.match(r"^## +", line):
            rest = re.sub(r"^## +\s*", "", line)
            out.append(f"**{rest}**" if rest else line)
        elif re.match(r"^# +", line):
            rest = re.sub(r"^# +\s*", "", line)
            out.append(f"**{rest}**" if rest else line)
        else:
            out.append(line)
    return "\n".join(out)


def _wrap_in_toggle(body):
    """本文を1つのトグル（<details>）で包み、いっぺんに開閉できるようにする。"""
    flattened = _flatten_notion_headings(body)
    return f"<details>\n<summary>本文を開く</summary>\n\n{flattened}\n\n</details>"


# エントリ先頭行（sort_yoritoori_entries と同様）
_ENTRY_HEADER = re.compile(r"^### \d{4}/\d{2}/\d{2}(?:\s+\d{1,2}:\d{2})?｜")
_CHATWORK_NOISE_RE = re.compile(
    r"\[dtext:chatroom_chat_joined\]|\[deleted\]|チャットに参加しました。",
    re.IGNORECASE,
)


def _split_into_blocks(body):
    """本文をブロック（### YYYY/MM/DD で始まるエントリ単位）に分割。"""
    blocks = []
    current = []
    for line in body.split("\n"):
        if _ENTRY_HEADER.match(line):
            if current:
                blocks.append("\n".join(current))
            current = [line]
        else:
            current.append(line)
    if current:
        blocks.append("\n".join(current))
    return blocks


def rewrite_existing_chatwork_blocks(md_path):
    """
    既存のやり取り.md のうち、（Chatwork）のブロックの本文を
    トグル＋Notion見出しの平坦化に書き換える。
    """
    md_path = Path(md_path)
    if not md_path.exists():
        return False, f"ファイルがありません: {md_path}"

    content = md_path.read_text(encoding="utf-8")
    if "## やり取り（時系列）" not in content:
        return False, "セクション見つからず"

    parts = content.split("## やり取り（時系列）", 1)
    header = parts[0] + "## やり取り（時系列）\n\n"
    body = parts[1]

    blocks = _split_into_blocks(body)
    new_blocks = []
    for b in blocks:
        lines = b.split("\n")
        first = lines[0]
        if "（Chatwork）" not in first:
            new_blocks.append(b)
            continue
        body_lines = lines[1:]
        body_text = "\n".join(body_lines).rstrip()
        body_text = re.sub(r"\n---\s*$", "", body_text)
        wrapped = _wrap_in_toggle(body_text)
        new_blocks.append(first + "\n\n" + wrapped + "\n\n---")
    new_content = header + "\n\n".join(new_blocks) + "\n"
    md_path.write_text(new_content, encoding="utf-8")
    return True, f"Chatworkブロックをトグル化しました（{len([b for b in blocks if '（Chatwork）' in b.split(chr(10))[0]])} 件）"


def cleanup_chatwork_noise_blocks(md_path):
    """
    既存のやり取り.md から Chatwork ノイズ投稿（参加通知・deleted など）の
    エントリブロックを除去する。
    """
    md_path = Path(md_path)
    if not md_path.exists():
        return False, f"ファイルがありません: {md_path}"

    content = md_path.read_text(encoding="utf-8")
    if "## やり取り（時系列）" not in content:
        return False, "セクション見つからず"

    parts = content.split("## やり取り（時系列）", 1)
    header = parts[0] + "## やり取り（時系列）\n\n"
    body = parts[1]
    blocks = _split_into_blocks(body)

    kept = []
    removed = 0
    for b in blocks:
        first = b.split("\n", 1)[0]
        if "（Chatwork）" not in first:
            kept.append(b)
            continue
        if _CHATWORK_NOISE_RE.search(b):
            removed += 1
            continue
        kept.append(b)

    new_content = header + "\n\n".join(kept).rstrip() + "\n"
    md_path.write_text(new_content, encoding="utf-8")
    return True, f"Chatworkノイズ投稿を削除しました（{removed} 件）"


def _chatwork_channel_label(room_name: str) -> str:
    name = (room_name or "").strip()
    if name:
        return f"Chatwork・{name}"
    return "Chatwork"


def download_chatwork_file(session, room_id: str, file_id: str) -> tuple[bytes, str]:
    """
    Chatwork ファイル API でバイナリとファイル名を取得。
    GET /rooms/{room_id}/files/{file_id}?create_download_url=1
    """
    meta_url = f"{CHATWORK_API_BASE}/rooms/{room_id}/files/{file_id}"
    resp = session.get(meta_url, params={"create_download_url": 1}, timeout=30)
    if resp.status_code == 404:
        raise FileNotFoundError(f"file_id={file_id} room_id={room_id} が見つかりません")
    if resp.status_code == 401:
        raise RuntimeError("Chatwork API トークンが無効です。CHATWORK_API_TOKEN を確認してください。")
    resp.raise_for_status()
    meta = resp.json() if resp.content else {}
    if not isinstance(meta, dict):
        meta = {}
    download_url = (
        meta.get("download_url")
        or meta.get("downloadUrl")
        or meta.get("url")
        or ""
    ).strip()
    api_filename = str(meta.get("filename") or meta.get("file_name") or "").strip()
    if not download_url:
        raise RuntimeError(f"download_url が取得できませんでした (file_id={file_id})")
    file_resp = session.get(download_url, timeout=120)
    file_resp.raise_for_status()
    return file_resp.content, api_filename


def download_chatwork_file_any_room(
    session, room_ids: list[str], file_id: str
) -> tuple[bytes, str, str]:
    """複数 room_id を順に試し、(bytes, filename, room_id) を返す。"""
    last_err: Exception | None = None
    for rid in room_ids:
        rid = str(rid).strip()
        if not rid:
            continue
        try:
            data, name = download_chatwork_file(session, rid, file_id)
            return data, name, rid
        except FileNotFoundError as e:
            last_err = e
            continue
        except requests.HTTPError as e:
            if e.response is not None and e.response.status_code in (403, 404):
                last_err = e
                continue
            raise
    raise FileNotFoundError(
        f"file_id={file_id} をいずれのルームでも取得できませんでした: {last_err}"
    )


def save_chatwork_attachments(
    session,
    room_id: str,
    folder_path: str,
    date_str: str,
    downloads: list[tuple[str, str]],
    *,
    room_ids: list[str] | None = None,
) -> list[str]:
    """
    Chatwork 添付を 1.受信添付(Stock)/YYYY-MM-DD/ に保存。
    戻り値: MD 用相対パス ["YYYY-MM-DD/保存名", ...]
    """
    if not downloads:
        return []

    partner_dir = BASE_PATH / folder_path
    ensure_incoming_stock_dir(partner_dir)
    attach_dir = resolve_incoming_attach_date_dir(partner_dir, date_str)
    date_folder = parse_received_date_folder(date_str)
    date_prefix = date_str.replace("/", "").replace(" ", "_")

    rooms = [str(x).strip() for x in (room_ids or [room_id]) if str(x).strip()]
    if room_id and str(room_id).strip() not in rooms:
        rooms.insert(0, str(room_id).strip())

    saved: list[str] = []
    for i, (file_id, display_name) in enumerate(downloads):
        try:
            buf, api_name, _used_room = download_chatwork_file_any_room(
                session, rooms, file_id
            )
        except Exception as e:
            print(
                f"  添付取得失敗 file_id={file_id}: {e}",
                file=sys.stderr,
            )
            continue

        raw_name = api_name or display_name or f"file_{file_id}"
        safe = sanitize_filename(raw_name)
        ext = os.path.splitext(safe)[1]
        base_name = os.path.splitext(safe)[0]

        if len(downloads) > 1:
            dest_path = attach_dir / f"{date_prefix}_{base_name}_{i + 1}{ext}"
        else:
            dest_path = attach_dir / f"{date_prefix}_{safe}"

        counter = 0
        while dest_path.exists():
            # 同一内容の再保存を避ける（サイズ一致ならそのパスを採用）
            try:
                if dest_path.stat().st_size == len(buf):
                    break
            except OSError:
                pass
            counter += 1
            stem, suf = dest_path.stem, dest_path.suffix
            dest_path = attach_dir / f"{stem}_{counter}{suf}"

        if not dest_path.exists() or dest_path.stat().st_size != len(buf):
            dest_path.write_bytes(buf)
        rel = f"{date_folder}/{dest_path.name}"
        saved.append(rel)
        print(f"  添付保存: {folder_path}/1.受信添付(Stock)/{rel}")

    return saved


def _attach_block(attachment_names: list[str] | None) -> str:
    if not attachment_names:
        return ""
    return "\n**添付ファイル**: " + ", ".join(attachment_names) + "（添付フォルダに保存）\n"


def append_to_yoritoori(
    folder_path,
    partner_name,
    date_str,
    body,
    *,
    room_name: str = "",
    attachment_names: list[str] | None = None,
):
    """相手からのメッセージをやり取り.md に追記。"""
    md_path = BASE_PATH / folder_path / YORITOORI_FILENAME
    if not md_path.exists():
        print(f"{YORITOORI_FILENAME} が見つかりません: {md_path}", file=sys.stderr)
        return False

    summary = make_summary(body)
    body_display = _wrap_in_toggle(body)
    channel = _chatwork_channel_label(room_name)
    attach = _attach_block(attachment_names)
    block = f"""

### {date_str}｜{partner_name}｜相手から返信（{channel}）｜{summary}

{body_display}
{attach}
---
"""
    content = md_path.read_text(encoding="utf-8")
    marker = "## やり取り（時系列）"
    if marker in content:
        pos = content.find(marker) + len(marker)
        content = content[:pos].rstrip() + "\n\n" + block.strip() + "\n\n" + content[pos:].lstrip()
    else:
        content += block
    md_path.write_text(content, encoding="utf-8")
    mirror_yoritoori_md_to_gitrepos(md_path)
    return True


def append_sent_to_yoritoori(
    folder_path,
    partner_name,
    date_str,
    body,
    *,
    room_name: str = "",
    attachment_names: list[str] | None = None,
):
    """自分から送ったメッセージをやり取り.md に「自分から送信（Chatwork）」として追記。"""
    md_path = BASE_PATH / folder_path / YORITOORI_FILENAME
    if not md_path.exists():
        print(f"{YORITOORI_FILENAME} が見つかりません: {md_path}", file=sys.stderr)
        return False

    summary = make_summary(body)
    body_display = _wrap_in_toggle(body)
    channel = _chatwork_channel_label(room_name)
    attach = _attach_block(attachment_names)
    block = f"""

### {date_str}｜{partner_name}｜自分から送信（{channel}）｜{summary}

{body_display}
{attach}
---
"""
    content = md_path.read_text(encoding="utf-8")
    marker = "## やり取り（時系列）"
    if marker in content:
        pos = content.find(marker) + len(marker)
        content = content[:pos].rstrip() + "\n\n" + block.strip() + "\n\n" + content[pos:].lstrip()
    else:
        content += block
    md_path.write_text(content, encoding="utf-8")
    mirror_yoritoori_md_to_gitrepos(md_path)
    return True


def get_my_account_id(session):
    resp = session.get(f"{CHATWORK_API_BASE}/me", timeout=20)
    resp.raise_for_status()
    data = resp.json()
    return int(data["account_id"])


def get_rooms(session):
    """参加ルーム一覧を取得。room_id 確認用。"""
    resp = session.get(f"{CHATWORK_API_BASE}/rooms", timeout=20)
    if resp.status_code == 401:
        raise RuntimeError("Chatwork API トークンが無効です。CHATWORK_API_TOKEN を確認してください。")
    resp.raise_for_status()
    data = resp.json()
    return data if isinstance(data, list) else []


def get_room_messages(session, room_id):
    url = f"{CHATWORK_API_BASE}/rooms/{room_id}/messages"
    resp = session.get(url, params={"force": 1}, timeout=30)
    if resp.status_code == 404:
        raise RuntimeError(f"room_id={room_id} が見つかりません。連絡先一覧.yaml を確認してください。")
    if resp.status_code == 401:
        raise RuntimeError("Chatwork API トークンが無効です。CHATWORK_API_TOKEN を確認してください。")
    resp.raise_for_status()
    data = resp.json()
    if not isinstance(data, list):
        return []
    return data


def load_partners(partner_filter):
    if not CONTACT_PATH.exists():
        raise RuntimeError(f"連絡先一覧が見つかりません: {CONTACT_PATH}")

    config = yaml.safe_load(CONTACT_PATH.read_text(encoding="utf-8")) or {}
    partners = config.get("partners", [])
    if not isinstance(partners, list):
        return []

    target = []
    for p in partners:
        room_ids = []
        raw_room_id = p.get("chatwork_room_id", "")
        if isinstance(raw_room_id, list):
            room_ids.extend([str(x).strip() for x in raw_room_id if str(x).strip()])
        else:
            raw = str(raw_room_id).strip()
            if raw:
                if "," in raw:
                    room_ids.extend([x.strip() for x in raw.split(",") if x.strip()])
                else:
                    room_ids.append(raw)
        # 将来拡張用: chatwork_room_ids も受け付ける
        raw_room_ids = p.get("chatwork_room_ids", [])
        if isinstance(raw_room_ids, list):
            room_ids.extend([str(x).strip() for x in raw_room_ids if str(x).strip()])
        if not room_ids:
            continue
        rooms_name_map: dict[str, str] = {}
        raw_rooms = p.get("chatwork_rooms", {})
        if isinstance(raw_rooms, dict):
            rooms_name_map = {
                str(k).strip(): str(v).strip()
                for k, v in raw_rooms.items()
                if str(k).strip() and str(v).strip()
            }
        if partner_filter:
            key = partner_filter.lower()
            name = str(p.get("name", "")).lower()
            folder = str(p.get("folder", "")).lower()
            if key not in name and key not in folder:
                continue
        # 同一パートナーで複数room_idを処理できるように展開
        for rid in dict.fromkeys(room_ids):
            p_copy = copy.deepcopy(p)
            p_copy["chatwork_room_id"] = rid
            p_copy["chatwork_room_name"] = rooms_name_map.get(rid, "")
            target.append(p_copy)
    return target


def parse_message_id(raw_id):
    try:
        return int(str(raw_id).strip())
    except (TypeError, ValueError):
        return None


def _partner_room_ids(partner: dict) -> list[str]:
    """展開前の partner dict から room_id 一覧を得る。"""
    room_ids: list[str] = []
    raw_room_id = partner.get("chatwork_room_id", "")
    if isinstance(raw_room_id, list):
        room_ids.extend([str(x).strip() for x in raw_room_id if str(x).strip()])
    else:
        raw = str(raw_room_id).strip()
        if raw:
            if "," in raw:
                room_ids.extend([x.strip() for x in raw.split(",") if x.strip()])
            else:
                room_ids.append(raw)
    raw_room_ids = partner.get("chatwork_room_ids", [])
    if isinstance(raw_room_ids, list):
        room_ids.extend([str(x).strip() for x in raw_room_ids if str(x).strip()])
    # 展開後エントリは chatwork_room_id が単一文字列
    return list(dict.fromkeys(room_ids))


def load_partners_unique(partner_filter):
    """パートナー単位（room 展開なし）で返す。バックフィル用。"""
    if not CONTACT_PATH.exists():
        raise RuntimeError(f"連絡先一覧が見つかりません: {CONTACT_PATH}")

    config = yaml.safe_load(CONTACT_PATH.read_text(encoding="utf-8")) or {}
    partners = config.get("partners", [])
    if not isinstance(partners, list):
        return []

    target = []
    for p in partners:
        room_ids = _partner_room_ids(p)
        if not room_ids:
            continue
        if partner_filter:
            key = partner_filter.lower()
            name = str(p.get("name", "")).lower()
            folder = str(p.get("folder", "")).lower()
            if key not in name and key not in folder:
                continue
        p_copy = copy.deepcopy(p)
        p_copy["_all_room_ids"] = room_ids
        target.append(p_copy)
    return target


def process_partner(session, partner, my_account_id, state):
    folder = partner.get("folder", "")
    partner_name = partner.get("name", folder)
    room_id = str(partner.get("chatwork_room_id", "")).strip()
    room_name = str(partner.get("chatwork_room_name", "")).strip()
    target_account_name = str(partner.get("chatwork_account_name", "")).strip()
    room_state = state["rooms"].setdefault(room_id, {})
    last_id = parse_message_id(room_state.get("last_message_id")) or 0
    last_sent_id = parse_message_id(room_state.get("last_sent_message_id")) or 0

    messages = get_room_messages(session, room_id)
    messages = sorted(messages, key=lambda x: parse_message_id(x.get("message_id")) or 0)

    appended = 0
    new_last_id = last_id
    new_last_sent_id = last_sent_id

    for msg in messages:
        message_id = parse_message_id(msg.get("message_id"))
        if not message_id:
            continue

        account = msg.get("account") or {}
        sender_id = parse_message_id(account.get("account_id"))
        sender_name = str(account.get("name", "")).strip()
        raw_body = str(msg.get("body", "") or "")
        downloads = extract_chatwork_downloads(raw_body)
        body = clean_chatwork_body(raw_body)
        date_str = format_date_jst(msg.get("send_time"))

        if sender_id == my_account_id:
            # 自分の投稿 → 自分から送信（Chatwork）として追記
            if message_id <= last_sent_id:
                continue
            new_last_sent_id = max(new_last_sent_id, message_id)
            attachment_names = save_chatwork_attachments(
                session, room_id, folder, date_str, downloads
            )
            if append_sent_to_yoritoori(
                folder,
                partner_name,
                date_str,
                body or "（本文なし）",
                room_name=room_name,
                attachment_names=attachment_names,
            ):
                appended += 1
                label = room_name or room_id
                print(f"追記（送信）: {partner_name} ({label}) - {body[:40]}...")
            continue

        # 相手からの投稿 → 相手から返信（Chatwork）として追記
        if message_id <= last_id:
            continue
        if target_account_name and target_account_name not in sender_name:
            continue
        new_last_id = max(new_last_id, message_id)
        if not body and not downloads:
            continue
        attachment_names = save_chatwork_attachments(
            session, room_id, folder, date_str, downloads
        )
        if append_to_yoritoori(
            folder,
            partner_name,
            date_str,
            body or "（添付のみ）",
            room_name=room_name,
            attachment_names=attachment_names,
        ):
            appended += 1
            label = room_name or room_id
            print(f"追記: {partner_name} ({label}) - {sender_name} - {body[:40]}...")

    if new_last_id > last_id:
        room_state["last_message_id"] = str(new_last_id)
    if new_last_sent_id > last_sent_id:
        room_state["last_sent_message_id"] = str(new_last_sent_id)
    return appended


def _insert_attach_line_into_block(block: str, attachment_names: list[str]) -> str:
    """ブロックに **添付ファイル** 行が無ければ追記する。"""
    if not attachment_names:
        return block
    if "**添付ファイル**" in block:
        return block
    attach = _attach_block(attachment_names).strip()
    # --- 直前、またはトグル終了後に挿入
    if re.search(r"\n---\s*$", block.rstrip()):
        return re.sub(r"\n---\s*$", f"\n\n{attach}\n\n---", block.rstrip(), count=1)
    return block.rstrip() + f"\n\n{attach}\n"


def backfill_attachments(session, partner_filter=None) -> int:
    """
    既存 5.やり取り.md 内の [download:file_id] を受信添付へ保存し、
    該当ブロックへ **添付ファイル** 行を補完する。
    """
    partners = load_partners_unique(partner_filter)
    if not partners:
        print("chatwork_room_id が設定されたパートナーが見つかりませんでした。")
        return 0

    total_saved = 0
    for partner in partners:
        folder = partner.get("folder", "")
        room_ids = partner.get("_all_room_ids") or _partner_room_ids(partner)
        md_path = BASE_PATH / folder / YORITOORI_FILENAME
        if not md_path.exists():
            print(f"スキップ（MDなし）: {folder}")
            continue

        content = md_path.read_text(encoding="utf-8")
        if "## やり取り（時系列）" not in content:
            print(f"スキップ（セクションなし）: {folder}")
            continue

        parts = content.split("## やり取り（時系列）", 1)
        header = parts[0] + "## やり取り（時系列）\n\n"
        body = parts[1]
        blocks = _split_into_blocks(body)
        changed = False
        partner_saved = 0

        for i, block in enumerate(blocks):
            downloads = extract_chatwork_downloads(block)
            if not downloads:
                continue
            first = block.split("\n", 1)[0]
            hm = re.match(
                r"^### (\d{4}/\d{2}/\d{2}(?:\s+\d{1,2}:\d{2})?)",
                first,
            )
            date_str = hm.group(1) if hm else datetime.now(JST).strftime("%Y/%m/%d %H:%M")

            # 既に **添付ファイル** があり、全 file_id 分のパスが揃っている場合はスキップ可だが、
            # ファイル実体が無ければ再取得する
            saved = save_chatwork_attachments(
                session,
                room_ids[0] if room_ids else "",
                folder,
                date_str,
                downloads,
                room_ids=room_ids,
            )
            if not saved:
                continue
            partner_saved += len(saved)
            total_saved += len(saved)
            new_block = _insert_attach_line_into_block(block, saved)
            if new_block != block:
                blocks[i] = new_block
                changed = True

        if changed:
            new_content = header + "\n\n".join(blocks).rstrip() + "\n"
            md_path.write_text(new_content, encoding="utf-8")
            mirror_yoritoori_md_to_gitrepos(md_path)
            print(f"バックフィル完了: {folder}（保存 {partner_saved} 件・MD更新）")
        elif partner_saved:
            print(f"バックフィル完了: {folder}（保存 {partner_saved} 件・MD変更なし）")
        else:
            print(f"バックフィル対象なし: {folder}")

    return total_saved


def main():
    parser = argparse.ArgumentParser(description="Chatwork のメッセージをやり取り.md に追記")
    parser.add_argument("--partner", help="対象パートナー名またはフォルダ名（部分一致）")
    parser.add_argument("--list-rooms", action="store_true", help="参加ルーム一覧を表示（room_id を連絡先一覧.yaml に記入する際に使用）")
    parser.add_argument("--rewrite-existing", metavar="FOLDER", help="既存のChatworkブロックをトグル化（例: 306_神大家AI推進）")
    parser.add_argument("--cleanup-noise", metavar="FOLDER", help="既存のChatworkノイズ投稿（参加通知・deleted）を削除（例: 907_Raimo代理店）")
    parser.add_argument(
        "--backfill-attachments",
        action="store_true",
        help="既存やり取り.md の [download:] を 1.受信添付(Stock) へ補完",
    )
    args = parser.parse_args()

    if args.rewrite_existing:
        folder_name = args.rewrite_existing.strip()
        md_path = BASE_PATH / folder_name / YORITOORI_FILENAME
        ok, msg = rewrite_existing_chatwork_blocks(md_path)
        if ok:
            print(msg)
        else:
            print(f"エラー: {msg}", file=sys.stderr)
            sys.exit(1)
        return

    if args.cleanup_noise:
        folder_name = args.cleanup_noise.strip()
        md_path = BASE_PATH / folder_name / YORITOORI_FILENAME
        ok, msg = cleanup_chatwork_noise_blocks(md_path)
        if ok:
            print(msg)
        else:
            print(f"エラー: {msg}", file=sys.stderr)
            sys.exit(1)
        return

    if not CHATWORK_API_TOKEN:
        print("エラー: CHATWORK_API_TOKEN が未設定です。", file=sys.stderr)
        print(f"  .env の候補: {SCRIPT_DIR / '.env'}", file=sys.stderr)
        print(f"  実行場所(cwd): {os.getcwd()}", file=sys.stderr)
        print("  → ターミナルで cd \"C1_cursor/1b_Cursorマニュアル\" のうえ、.env に CHATWORK_API_TOKEN=トークン の1行があるか確認してください。", file=sys.stderr)
        sys.exit(1)

    session = requests.Session()
    session.headers.update({"X-ChatWorkToken": CHATWORK_API_TOKEN})

    if args.list_rooms:
        try:
            rooms = get_rooms(session)
        except Exception as e:
            print(f"エラー: {e}", file=sys.stderr)
            sys.exit(1)
        if not rooms:
            print("参加中のルームがありません。")
            return
        print("参加中のルーム一覧（連絡先一覧.yaml の chatwork_room_id に room_id を記入してください）:\n")
        for r in rooms:
            room_id = r.get("room_id") or r.get("roomId") or ""
            name = r.get("name", "")
            rtype = r.get("type", "")
            print(f"  room_id: {room_id}  名前: {name}  type: {rtype}")
        return

    if args.backfill_attachments:
        try:
            n = backfill_attachments(session, args.partner)
        except Exception as e:
            print(f"エラー: {e}", file=sys.stderr)
            sys.exit(1)
        print(f"\nバックフィル合計: {n} 件の添付を保存しました。" if n else "\n保存した添付はありませんでした。")
        return

    try:
        targets = load_partners(args.partner)
    except RuntimeError as e:
        print(f"エラー: {e}", file=sys.stderr)
        sys.exit(1)

    if not targets:
        print("chatwork_room_id が設定されたパートナーが見つかりませんでした。")
        print("連絡先一覧.yaml の chatwork_room_id を設定してください。")
        print("room_id が分からない場合は: python chatwork_to_yoritoori.py --list-rooms")
        return

    try:
        my_account_id = get_my_account_id(session)
    except Exception as e:
        print(f"エラー: Chatwork API 接続に失敗しました: {e}", file=sys.stderr)
        sys.exit(1)

    state = load_processed()
    total = 0

    for partner in targets:
        try:
            total += process_partner(session, partner, my_account_id, state)
        except Exception as e:
            name = partner.get("name", partner.get("folder", ""))
            print(f"{name} の処理でエラー: {e}", file=sys.stderr)

    save_processed(state)

    if total > 0:
        print(f"\n{total} 件のメッセージをやり取りに追記しました。")
    else:
        print("追記対象の新規メッセージはありませんでした。")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n中断しました。", file=sys.stderr)
        sys.exit(130)
