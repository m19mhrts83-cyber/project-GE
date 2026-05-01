#!/usr/bin/env python3
"""
Chatwork API からメッセージを取得し、連絡先一覧.yaml の設定に従って
該当フォルダの 5.やり取り.md に追記する。

前提:
  - CHATWORK_API_TOKEN を環境変数または .env に設定
  - 連絡先一覧.yaml に chatwork_room_id を設定
  - pip install -r requirements_gmail.txt 済み（requests / PyYAML を使用）

使い方:
  python chatwork_to_yoritoori.py
  python chatwork_to_yoritoori.py --partner 神大家AI推進
  python chatwork_to_yoritoori.py --list-rooms   # room_id 確認用（トークン設定後に実行）
  python chatwork_to_yoritoori.py --rewrite-existing 306_神大家AI推進   # 既存のChatworkブロックをトグル化
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


def append_to_yoritoori(folder_path, partner_name, date_str, body):
    """相手からのメッセージをやり取り.md に追記。"""
    md_path = BASE_PATH / folder_path / YORITOORI_FILENAME
    if not md_path.exists():
        print(f"{YORITOORI_FILENAME} が見つかりません: {md_path}", file=sys.stderr)
        return False

    summary = make_summary(body)
    body_display = _wrap_in_toggle(body)
    block = f"""

### {date_str}｜{partner_name}｜相手から返信（Chatwork）｜{summary}

{body_display}

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


def append_sent_to_yoritoori(folder_path, partner_name, date_str, body):
    """自分から送ったメッセージをやり取り.md に「自分から送信（Chatwork）」として追記。"""
    md_path = BASE_PATH / folder_path / YORITOORI_FILENAME
    if not md_path.exists():
        print(f"{YORITOORI_FILENAME} が見つかりません: {md_path}", file=sys.stderr)
        return False

    summary = make_summary(body)
    body_display = _wrap_in_toggle(body)
    block = f"""

### {date_str}｜{partner_name}｜自分から送信（Chatwork）｜{summary}

{body_display}

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
            target.append(p_copy)
    return target


def parse_message_id(raw_id):
    try:
        return int(str(raw_id).strip())
    except (TypeError, ValueError):
        return None


def process_partner(session, partner, my_account_id, state):
    folder = partner.get("folder", "")
    partner_name = partner.get("name", folder)
    room_id = str(partner.get("chatwork_room_id", "")).strip()
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
        body = clean_chatwork_body(msg.get("body", ""))
        date_str = format_date_jst(msg.get("send_time"))

        if sender_id == my_account_id:
            # 自分の投稿 → 自分から送信（Chatwork）として追記
            if message_id <= last_sent_id:
                continue
            new_last_sent_id = max(new_last_sent_id, message_id)
            if append_sent_to_yoritoori(folder, partner_name, date_str, body or "（本文なし）"):
                appended += 1
                print(f"追記（送信）: {partner_name} (room:{room_id}) - {body[:40]}...")
            continue

        # 相手からの投稿 → 相手から返信（Chatwork）として追記
        if message_id <= last_id:
            continue
        if target_account_name and target_account_name not in sender_name:
            continue
        new_last_id = max(new_last_id, message_id)
        if not body:
            continue
        if append_to_yoritoori(folder, partner_name, date_str, body):
            appended += 1
            print(f"追記: {partner_name} (room:{room_id}) - {sender_name} - {body[:40]}...")

    if new_last_id > last_id:
        room_state["last_message_id"] = str(new_last_id)
    if new_last_sent_id > last_sent_id:
        room_state["last_sent_message_id"] = str(new_last_sent_id)
    return appended


def main():
    parser = argparse.ArgumentParser(description="Chatwork のメッセージをやり取り.md に追記")
    parser.add_argument("--partner", help="対象パートナー名またはフォルダ名（部分一致）")
    parser.add_argument("--list-rooms", action="store_true", help="参加ルーム一覧を表示（room_id を連絡先一覧.yaml に記入する際に使用）")
    parser.add_argument("--rewrite-existing", metavar="FOLDER", help="既存のChatworkブロックをトグル化（例: 306_神大家AI推進）")
    parser.add_argument("--cleanup-noise", metavar="FOLDER", help="既存のChatworkノイズ投稿（参加通知・deleted）を削除（例: 907_Raimo代理店）")
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
