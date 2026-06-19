#!/usr/bin/env python3
"""一回限り: 806 神大家AI推進の送信下書きを Chatwork ルームへ POST し、やり取り.md に追記する。"""
import os
import re
import sys
from datetime import datetime
from pathlib import Path

import requests
import yaml

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from yoritoori_send import parse_draft, base_path, contact_path, trigger_editor_save_all  # noqa: E402
from yoritoori_utils import YORITOORI_FILENAME, make_summary  # noqa: E402


def load_env():
    p = SCRIPT_DIR / ".env"
    if not p.exists():
        return
    for line in p.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^\s*([^#=]+)\s*=\s*(.+?)\s*$", line)
        if m:
            k, v = m.group(1).strip(), m.group(2).strip().strip("\"'")
            if v:
                os.environ[k] = v


def append_chatwork_block(folder_path: str, partner_name: str, subject: str, body: str) -> None:
    md_path = base_path / folder_path / YORITOORI_FILENAME
    if not md_path.exists():
        raise FileNotFoundError(str(md_path))
    date_str = datetime.now().strftime("%Y/%m/%d %H:%M")
    summary = make_summary(body, max_len=50)
    subject_block = f"**件名**: {subject}\n" if subject else ""
    block = f"""

### {date_str}｜{partner_name}｜自分から送信（Chatwork）｜{summary}

{subject_block}{body}

---
"""
    content = md_path.read_text(encoding="utf-8")
    marker = "## やり取り（時系列）"
    if marker in content:
        after_marker = content[content.find(marker) :]
        m = re.search(r"\n\n### [12]\d{3}/\d{2}/\d{2}", after_marker)
        if m:
            pos = content.find(marker) + m.start() + 2
            content = content[:pos] + block.strip() + "\n\n" + content[pos:]
        else:
            pos = content.find(marker) + len(marker)
            content = content[:pos].rstrip() + "\n\n" + block.strip() + "\n\n" + content[pos:].lstrip()
    else:
        content += block
    md_path.write_text(content, encoding="utf-8")


def main():
    load_env()
    token = os.environ.get("CHATWORK_API_TOKEN", "").strip()
    if not token:
        print("エラー: CHATWORK_API_TOKEN が .env にありません。", file=sys.stderr)
        sys.exit(1)

    cfg = yaml.safe_load(contact_path.read_text(encoding="utf-8"))
    partner = next(
        (p for p in cfg.get("partners", []) if p.get("folder") == "806_神大家AI推進"),
        None,
    )
    if not partner:
        print("エラー: 806_神大家AI推進 が連絡先一覧にありません。", file=sys.stderr)
        sys.exit(1)
    room_id = (partner.get("chatwork_room_id") or "").strip()
    if not room_id:
        print("エラー: chatwork_room_id が未設定です。", file=sys.stderr)
        sys.exit(1)

    folder_path = partner["folder"]
    partner_name = partner["name"]
    draft_path = base_path / folder_path / "4.送信下書き.txt"
    if not trigger_editor_save_all():
        print(
            "エラー: Cursor の「すべて保存」に失敗しました。Cursor を前面にして再実行してください。",
            file=sys.stderr,
        )
        sys.exit(1)
    subject, body = parse_draft(draft_path)
    if not body.strip():
        print("エラー: 送信下書きが空です。", file=sys.stderr)
        sys.exit(1)

    url = f"https://api.chatwork.com/v2/rooms/{room_id}/messages"
    r = requests.post(
        url,
        headers={"X-ChatWorkToken": token},
        data={"body": body},
        timeout=60,
    )
    if not r.ok:
        print(f"Chatwork API エラー: {r.status_code} {r.text}", file=sys.stderr)
        sys.exit(1)

    append_chatwork_block(folder_path, partner_name, subject, body)
    print("Chatwork へ送信しました。5.やり取り.md に追記しました。")
    print(r.json())


if __name__ == "__main__":
    main()
