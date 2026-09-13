#!/usr/bin/env python3
"""
GHA / クラウド: パートナー Chatwork → OneDrive `5.やり取り.md`（Graph 書込）。

添付は Graph で `1.受信添付(Stock)/YYYY-MM-DD/` へ保存（API 取得可能分）。
進捗は OneDrive 共通 JSON（Mac の chatwork_to_yoritoori と共有）。

  cd ~/git-repos && set -a && source .env.jarvis_private && set +a
  PYTHONPATH=scripts:215_kamiooya/C1_cursor/1b_Cursorマニュアル \\
    python scripts/jarvis_gha_partner_chatwork_yoritoori.py --dry-run
  python scripts/jarvis_gha_partner_chatwork_yoritoori.py --apply
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
MANUAL = REPO / "215_kamiooya" / "C1_cursor" / "1b_Cursorマニュアル"
PARTNER_BASE_REL = (
    "215_神・大家さん倶楽部/C2_ルーティン作業/26_パートナー社への相談"
)
CONTACT_REL = f"{PARTNER_BASE_REL}/000_共通/連絡先一覧.yaml"
STATE_REL = f"{PARTNER_BASE_REL}/000_共通/.jarvis_chatwork_processed.json"
CONTACT_CI = MANUAL / "連絡先一覧.snapshot.yaml"

sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, str(MANUAL))

_NOISE_RE = re.compile(
    r"\[dtext:chatroom_chat_joined\]|\[deleted\]|チャットに参加しました。",
    re.IGNORECASE,
)


def materialize_contact_yaml(tmp: Path) -> Path:
    from jarvis_onedrive_graph import graph_configured, read_file

    dest = tmp / "連絡先一覧.yaml"
    if graph_configured():
        try:
            dest.write_bytes(read_file("onedrive", CONTACT_REL))
            print(f"# contact: graph {CONTACT_REL}", file=sys.stderr)
            return dest
        except Exception as e:
            print(f"# contact graph fail: {e}", file=sys.stderr)
    local = Path.home() / "Library/CloudStorage/OneDrive-個人用" / CONTACT_REL
    if local.is_file():
        dest.write_bytes(local.read_bytes())
        print(f"# contact: local {local}", file=sys.stderr)
        return dest
    if CONTACT_CI.is_file():
        dest.write_bytes(CONTACT_CI.read_bytes())
        print(f"# contact: snapshot {CONTACT_CI}", file=sys.stderr)
        return dest
    raise SystemExit("連絡先一覧.yaml を取得できません")


def yoritoori_rel(folder: str) -> str:
    return f"{PARTNER_BASE_REL}/{folder}/5.やり取り.md"


def attach_rel(folder: str, date_folder: str, name: str) -> str:
    return f"{PARTNER_BASE_REL}/{folder}/1.受信添付(Stock)/{date_folder}/{name}"


def load_state() -> dict[str, Any]:
    from jarvis_onedrive_graph import graph_configured, read_file

    if graph_configured():
        try:
            raw = read_file("onedrive", STATE_REL)
            data = json.loads(raw.decode("utf-8", errors="replace"))
            if isinstance(data, dict):
                data.setdefault("rooms", {})
                return data
        except FileNotFoundError:
            pass
        except Exception as e:
            msg = str(e)
            if "404" in msg or "itemNotFound" in msg:
                print("# state: graph not found yet (will create on apply)", file=sys.stderr)
            else:
                print(f"# state graph read fail: {e}", file=sys.stderr)
    local = Path.home() / "Library/CloudStorage/OneDrive-個人用" / STATE_REL
    if local.is_file():
        try:
            data = json.loads(local.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                data.setdefault("rooms", {})
                return data
        except Exception:
            pass
    legacy = Path.home() / ".cursor" / "chatwork_processed.json"
    if legacy.is_file():
        try:
            data = json.loads(legacy.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                data.setdefault("rooms", {})
                print(f"# state: migrated from {legacy}", file=sys.stderr)
                return data
        except Exception:
            pass
    return {"rooms": {}}


def save_state(state: dict[str, Any], *, dry_run: bool) -> None:
    from jarvis_onedrive_graph import graph_configured, write_file

    payload = json.dumps(state, ensure_ascii=False, indent=2) + "\n"
    if dry_run:
        print(f"# dry-run would save state rooms={len(state.get('rooms') or {})}", file=sys.stderr)
        return
    data = payload.encode("utf-8")
    if graph_configured():
        write_file("onedrive", STATE_REL, data)
        print(f"# state: graph wrote {STATE_REL}", file=sys.stderr)
        return
    local = Path.home() / "Library/CloudStorage/OneDrive-個人用" / STATE_REL
    local.parent.mkdir(parents=True, exist_ok=True)
    local.write_bytes(data)
    print(f"# state: local wrote {local}", file=sys.stderr)


def parse_message_id(raw_id: Any) -> int | None:
    try:
        return int(str(raw_id).strip())
    except (TypeError, ValueError):
        return None


def channel_label(room_name: str) -> str:
    name = (room_name or "").strip()
    if name:
        return f"Chatwork・{name}"
    return "Chatwork"


def attach_line(names: list[str]) -> str:
    if not names:
        return ""
    return "\n**添付ファイル**: " + ", ".join(names) + "（添付フォルダに保存）\n"


def build_block(
    *,
    partner_name: str,
    date_str: str,
    body: str,
    room_name: str,
    inbound: bool,
    attachment_names: list[str] | None,
) -> str:
    from chatwork_to_yoritoori import _wrap_in_toggle  # type: ignore
    from yoritoori_utils import make_summary

    summary = make_summary(body)
    body_display = _wrap_in_toggle(body)
    channel = channel_label(room_name)
    direction = "相手から返信" if inbound else "自分から送信"
    attach = attach_line(attachment_names or [])
    return f"""

### {date_str}｜{partner_name}｜{direction}（{channel}）｜{summary}

{body_display}
{attach}
---
"""


def save_attachments_graph(
    session: Any,
    room_id: str,
    folder: str,
    date_str: str,
    downloads: list[tuple[str, str]],
    *,
    dry_run: bool,
) -> list[str]:
    """[(file_id, display_hint)] → relative paths under Stock."""
    if not downloads:
        return []
    from chatwork_to_yoritoori import download_chatwork_file  # type: ignore
    from jarvis_onedrive_graph import graph_configured, write_file
    from yoritoori_utils import parse_received_date_folder

    date_folder = parse_received_date_folder(date_str) or date_str[:10].replace("/", "-")
    saved: list[str] = []
    for file_id, hint in downloads:
        try:
            buf, api_name = download_chatwork_file(session, room_id, file_id)
        except Exception as e:
            print(f"# attach download fail {file_id}: {e}", file=sys.stderr)
            continue
        name = (api_name or hint or f"file_{file_id}").strip() or f"file_{file_id}"
        name = re.sub(r"[\\/]+", "_", name)
        rel_name = f"{date_folder}/{name}"
        graph_path = attach_rel(folder, date_folder, name)
        if dry_run:
            print(f"# dry-run attach {graph_path} bytes={len(buf)}", file=sys.stderr)
            saved.append(rel_name)
            continue
        try:
            if graph_configured():
                write_file("onedrive", graph_path, buf)
            else:
                local = Path.home() / "Library/CloudStorage/OneDrive-個人用" / graph_path
                local.parent.mkdir(parents=True, exist_ok=True)
                local.write_bytes(buf)
            saved.append(rel_name)
            print(f"# attach ok {folder}/{rel_name}", file=sys.stderr)
        except Exception as e:
            print(f"# attach write fail {graph_path}: {e}", file=sys.stderr)
    return saved


def append_block_graph(folder: str, block: str, *, dry_run: bool) -> bool:
    from jarvis_onedrive_graph import append_text_graph, graph_configured
    from yoritoori_utils import insert_after_timeline_heading

    rel = yoritoori_rel(folder)
    if dry_run:
        print(f"# dry-run would append {folder} ({len(block)} chars)", file=sys.stderr)
        return True

    def transform(old: str, _b: str) -> str:
        return insert_after_timeline_heading(old, block)

    if graph_configured():
        append_text_graph(rel, "", transform=transform)
        return True
    local = Path.home() / "Library/CloudStorage/OneDrive-個人用" / rel
    if not local.is_file():
        print(f"# md missing {local}", file=sys.stderr)
        return False
    local.write_text(transform(local.read_text(encoding="utf-8"), ""), encoding="utf-8")
    return True


def process_partner(
    session: Any,
    partner: dict[str, Any],
    my_account_id: int,
    state: dict[str, Any],
    *,
    dry_run: bool,
) -> dict[str, int]:
    from chatwork_to_yoritoori import (  # type: ignore
        clean_chatwork_body,
        extract_chatwork_downloads,
        format_date_jst,
        get_room_messages,
    )

    stats = {"appended": 0, "skipped": 0, "noise": 0, "fail": 0}
    folder = partner.get("folder", "")
    partner_name = partner.get("name", folder)
    room_id = str(partner.get("chatwork_room_id", "")).strip()
    room_name = str(partner.get("chatwork_room_name", "")).strip()
    target_account_name = str(partner.get("chatwork_account_name", "")).strip()
    if not folder or not room_id:
        return stats

    room_state = state.setdefault("rooms", {}).setdefault(room_id, {})
    last_id = parse_message_id(room_state.get("last_message_id")) or 0
    last_sent_id = parse_message_id(room_state.get("last_sent_message_id")) or 0

    try:
        messages = get_room_messages(session, room_id)
    except Exception as e:
        print(f"# room fail {partner_name} {room_id}: {e}", file=sys.stderr)
        stats["fail"] += 1
        return stats

    messages = sorted(messages, key=lambda x: parse_message_id(x.get("message_id")) or 0)
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
        if _NOISE_RE.search(raw_body):
            if sender_id == my_account_id:
                if message_id > last_sent_id:
                    new_last_sent_id = max(new_last_sent_id, message_id)
            elif message_id > last_id:
                new_last_id = max(new_last_id, message_id)
            stats["noise"] += 1
            continue

        downloads = extract_chatwork_downloads(raw_body)
        body = clean_chatwork_body(raw_body)
        date_str = format_date_jst(msg.get("send_time"))

        if sender_id == my_account_id:
            if message_id <= last_sent_id:
                stats["skipped"] += 1
                continue
            new_last_sent_id = max(new_last_sent_id, message_id)
            attach_names = save_attachments_graph(
                session, room_id, folder, date_str, downloads, dry_run=dry_run
            )
            block = build_block(
                partner_name=partner_name,
                date_str=date_str,
                body=body or "（本文なし）",
                room_name=room_name,
                inbound=False,
                attachment_names=attach_names,
            )
            try:
                if append_block_graph(folder, block, dry_run=dry_run):
                    stats["appended"] += 1
                    print(
                        f"# appended sent {partner_name} mid={message_id}",
                        file=sys.stderr,
                    )
            except Exception as e:
                print(f"# append sent fail {partner_name}: {e}", file=sys.stderr)
                stats["fail"] += 1
            continue

        if message_id <= last_id:
            stats["skipped"] += 1
            continue
        if target_account_name and target_account_name not in sender_name:
            stats["skipped"] += 1
            continue
        new_last_id = max(new_last_id, message_id)
        if not body and not downloads:
            stats["skipped"] += 1
            continue
        attach_names = save_attachments_graph(
            session, room_id, folder, date_str, downloads, dry_run=dry_run
        )
        block = build_block(
            partner_name=partner_name,
            date_str=date_str,
            body=body or "（添付のみ）",
            room_name=room_name,
            inbound=True,
            attachment_names=attach_names,
        )
        try:
            if append_block_graph(folder, block, dry_run=dry_run):
                stats["appended"] += 1
                print(
                    f"# appended in {partner_name} mid={message_id} from={sender_name}",
                    file=sys.stderr,
                )
        except Exception as e:
            print(f"# append in fail {partner_name}: {e}", file=sys.stderr)
            stats["fail"] += 1

    if new_last_id > last_id:
        room_state["last_message_id"] = str(new_last_id)
    if new_last_sent_id > last_sent_id:
        room_state["last_sent_message_id"] = str(new_last_sent_id)
    return stats


def run(*, dry_run: bool, partner_filter: str | None) -> dict[str, int]:
    import requests
    import yaml
    from chatwork_to_yoritoori import get_my_account_id, load_partners  # type: ignore

    token = (os.environ.get("CHATWORK_API_TOKEN") or "").strip()
    if not token:
        raise SystemExit("CHATWORK_API_TOKEN 未設定")

    totals = {
        "partners": 0,
        "appended": 0,
        "skipped": 0,
        "noise": 0,
        "fail": 0,
        "dry_run": 1 if dry_run else 0,
    }

    with tempfile.TemporaryDirectory(prefix="jarvis_gha_cw_") as td:
        contact = materialize_contact_yaml(Path(td))
        os.environ["CONTACT_LIST_PATH"] = str(contact)
        # chatwork_to_yoritoori.load_partners は CONTACT_PATH をモジュール読込時に固定しているため再設定
        import chatwork_to_yoritoori as cw  # type: ignore

        cw.CONTACT_PATH = contact
        cw.CHATWORK_API_TOKEN = token

        partners = load_partners(partner_filter)
        if not partners:
            print("# no chatwork partners", file=sys.stderr)
            return totals

        session = requests.Session()
        session.headers.update({"X-ChatWorkToken": token})
        my_id = get_my_account_id(session)
        state = load_state()

        for partner in partners:
            totals["partners"] += 1
            st = process_partner(
                session, partner, my_id, state, dry_run=dry_run
            )
            for k in ("appended", "skipped", "noise", "fail"):
                totals[k] += st.get(k, 0)

        save_state(state, dry_run=dry_run)
    return totals


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--partner", default="", help="名前/フォルダ部分一致")
    args = ap.parse_args(argv)
    dry = not args.apply or args.dry_run
    if args.apply and args.dry_run:
        dry = True
    stats = run(dry_run=dry, partner_filter=args.partner.strip() or None)
    print(f"📎 partner chatwork→md: {stats}")
    return 0 if stats.get("fail", 0) == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
