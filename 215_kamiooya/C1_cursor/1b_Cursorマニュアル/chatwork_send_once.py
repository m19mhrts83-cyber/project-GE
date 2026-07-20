#!/usr/bin/env python3
"""806 神大家AI推進: 送信下書きを Chatwork ルームへ POST し、やり取り.md に追記する。

複数ルーム紐付け時は --room で送信先を明示する（未指定はエラー）。
"""
from __future__ import annotations

import argparse
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

FOLDER_806 = "806_神大家AI推進"
ROOM_ALIASES = {
    "meguro": "422374412",
    "meeting": "422374412",
    "dm": "422374412",
    "目黒": "422374412",
    "group": "439357504",
    "スクール": "439357504",
    "グループ": "439357504",
}


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


def _normalize_room_ids(raw) -> list[str]:
    if isinstance(raw, list):
        return [str(x).strip() for x in raw if str(x).strip()]
    text = str(raw or "").strip()
    if not text:
        return []
    if "," in text:
        return [x.strip() for x in text.split(",") if x.strip()]
    return [text]


def _room_name_map(partner: dict) -> dict[str, str]:
    out: dict[str, str] = {}
    raw = partner.get("chatwork_rooms", {})
    if isinstance(raw, dict):
        for rid, name in raw.items():
            key = str(rid).strip()
            label = str(name).strip()
            if key and label:
                out[key] = label
    return out


def _chatwork_channel_label(room_name: str) -> str:
    name = (room_name or "").strip()
    if name:
        return f"Chatwork・{name}"
    return "Chatwork"


def resolve_room(partner: dict, *, room: str | None, room_id: str | None) -> tuple[str, str]:
    """(room_id, room_name) を返す。複数ルームで未指定なら SystemExit。"""
    room_ids = _normalize_room_ids(partner.get("chatwork_room_id"))
    names = _room_name_map(partner)

    # 連絡先一覧.yaml の chatwork_room_id が正本。未登録のまま alias / --room-id で
    # 送信できてしまうと誤送信につながるため、空なら送信しない。
    if not room_ids:
        print(
            f"エラー: {FOLDER_806} の chatwork_room_id が連絡先一覧.yaml に登録されていません。"
            " 先に登録してから再実行してください。",
            file=sys.stderr,
        )
        sys.exit(1)

    if room_id:
        rid = str(room_id).strip()
        if rid not in room_ids:
            print(f"エラー: room_id={rid} は 806 の登録ルームではありません。", file=sys.stderr)
            sys.exit(1)
        return rid, names.get(rid, rid)

    if room:
        key = room.strip()
        rid = ROOM_ALIASES.get(key) or ROOM_ALIASES.get(key.lower())
        if not rid:
            # 表示名の部分一致
            for registered_id, label in names.items():
                if key in label or label in key:
                    rid = registered_id
                    break
        if not rid:
            print(
                f"エラー: --room '{room}' を解決できません。"
                " meguro（目黒 啓太）または group（スクール運営グループ）を指定してください。",
                file=sys.stderr,
            )
            sys.exit(1)
        if rid not in room_ids:
            print(f"エラー: room_id={rid} は 806 の登録ルームではありません。", file=sys.stderr)
            sys.exit(1)
        return rid, names.get(rid, rid)

    if len(room_ids) == 1:
        rid = room_ids[0]
        return rid, names.get(rid, rid)

    print("エラー: Chatwork 送信先が複数あります。--room を指定してください。", file=sys.stderr)
    print("  目黒さん（1:1）     → --room meguro", file=sys.stderr)
    print("  スクール運営グループ → --room group", file=sys.stderr)
    for rid in room_ids:
        print(f"    room_id={rid}  名前: {names.get(rid, '（未設定）')}", file=sys.stderr)
    sys.exit(1)


def append_chatwork_block(
    folder_path: str,
    partner_name: str,
    subject: str,
    body: str,
    *,
    room_name: str = "",
) -> None:
    md_path = base_path / folder_path / YORITOORI_FILENAME
    if not md_path.exists():
        raise FileNotFoundError(str(md_path))
    date_str = datetime.now().strftime("%Y/%m/%d %H:%M")
    summary = make_summary(body, max_len=50)
    subject_block = f"**件名**: {subject}\n" if subject else ""
    channel = _chatwork_channel_label(room_name)
    block = f"""

### {date_str}｜{partner_name}｜自分から送信（{channel}）｜{summary}

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
    parser = argparse.ArgumentParser(description=f"{FOLDER_806} の Chatwork 送信")
    parser.add_argument(
        "--room",
        help="送信先: meguro=目黒 啓太（1:1）, group=【神大家】松野さん・スクール運営社員",
    )
    parser.add_argument("--room-id", help="room_id を直接指定（上級者用）")
    args = parser.parse_args()

    load_env()
    token = os.environ.get("CHATWORK_API_TOKEN", "").strip()
    if not token:
        print("エラー: CHATWORK_API_TOKEN が .env にありません。", file=sys.stderr)
        sys.exit(1)

    cfg = yaml.safe_load(contact_path.read_text(encoding="utf-8"))
    partner = next(
        (p for p in cfg.get("partners", []) if p.get("folder") == FOLDER_806),
        None,
    )
    if not partner:
        print(f"エラー: {FOLDER_806} が連絡先一覧にありません。", file=sys.stderr)
        sys.exit(1)

    room_id, room_name = resolve_room(partner, room=args.room, room_id=args.room_id)

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

    append_chatwork_block(folder_path, partner_name, subject, body, room_name=room_name)
    label = room_name or room_id
    print(f"Chatwork へ送信しました（{label}）。5.やり取り.md に追記しました。")
    print(r.json())


if __name__ == "__main__":
    main()
