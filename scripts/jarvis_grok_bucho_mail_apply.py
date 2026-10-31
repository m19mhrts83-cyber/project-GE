#!/usr/bin/env python3
"""Grok 部長日報メール → 業者リスト --mark / 探索 YAML 自動反映。

部長 Bot が matsuno.estate@gmail.com へ送った `[Grok部長]` メールを estate Gmail API で読み、
本文の `--mark` 行と `📎 Jarvis 用（探索追記）` の vendors YAML を反映する。

  cd ~/git-repos
  ~/selenium_env/venv/bin/python scripts/jarvis_grok_bucho_mail_apply.py --dry-run
  ~/selenium_env/venv/bin/python scripts/jarvis_grok_bucho_mail_apply.py --apply

取込が済んだメールは受信トレイから外し、既読＋ラベル「Grok部長」にする（自分発信の機械連絡を
要対応判断に出さないため）。残したいときは JARVIS_GROK_BUCHO_KEEP_INBOX=1。

使用アカウント: estate / Gmail API（受信）
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

REPO = Path(__file__).resolve().parents[1]
MANUAL = REPO / "215_kamiooya" / "C1_cursor" / "1b_Cursorマニュアル"
STATE_PATH = REPO / ".jarvis_state" / "grok_bucho_mail_apply.json"
SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.modify",
]
BUCHO_PREFIX = "[Grok部長]"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_state() -> dict[str, Any]:
    if not STATE_PATH.is_file():
        return {"processed_ids": [], "last_run_at": None}
    try:
        data = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return {"processed_ids": [], "last_run_at": None}
        data.setdefault("processed_ids", [])
        return data
    except Exception:
        return {"processed_ids": [], "last_run_at": None}


def save_state(state: dict[str, Any]) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    state["last_run_at"] = now_iso()
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def gmail_service():
    path = MANUAL / "token_estate.json"
    if not path.is_file():
        raise FileNotFoundError(f"token not found: {path}")
    creds = Credentials.from_authorized_user_file(str(path), SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        path.write_text(creds.to_json(), encoding="utf-8")
    return build("gmail", "v1", credentials=creds, cache_discovery=False)


def decode_body(payload: dict) -> str:
    """Prefer text/plain. HTML is fallback only (avoids &quot; winning over clean --mark notes)."""
    import html as html_lib

    plains: list[str] = []
    htmls: list[str] = []

    def walk(part: dict) -> None:
        mime = (part.get("mimeType") or "").lower()
        body = part.get("body") or {}
        data = body.get("data")
        if data and mime in ("text/plain", "text/html"):
            raw = base64.urlsafe_b64decode(data + "==")
            text = raw.decode("utf-8", errors="replace")
            if mime == "text/html":
                text = re.sub(r"<br\s*/?>", "\n", text, flags=re.I)
                text = re.sub(r"</p>", "\n", text, flags=re.I)
                text = re.sub(r"<[^>]+>", " ", text)
                text = html_lib.unescape(text)
                text = re.sub(r"[ \t]+", " ", text)
                htmls.append(text)
            else:
                plains.append(text)
        for ch in part.get("parts") or []:
            walk(ch)

    walk(payload)
    chosen = plains if plains else htmls
    return "\n".join(chosen)[:50000]


def header_map(headers: list[dict]) -> dict[str, str]:
    out: dict[str, str] = {}
    for h in headers or []:
        out[(h.get("name") or "").lower()] = h.get("value") or ""
    return out


def fetch_bucho_messages(svc, *, days: int, max_results: int) -> list[dict[str, Any]]:
    q = f'subject:"{BUCHO_PREFIX}" newer_than:{days}d'
    res = (
        svc.users()
        .messages()
        .list(userId="me", q=q, maxResults=max_results)
        .execute()
    )
    out: list[dict[str, Any]] = []
    for item in res.get("messages") or []:
        mid = item.get("id")
        if not mid:
            continue
        msg = svc.users().messages().get(userId="me", id=mid, format="full").execute()
        hm = header_map(msg.get("payload", {}).get("headers") or [])
        out.append(
            {
                "id": mid,
                "subject": hm.get("subject", ""),
                "date": hm.get("date", ""),
                "label_ids": list(msg.get("labelIds") or []),
                "body": decode_body(msg.get("payload") or {}),
            }
        )
    return out


BUCHO_LABEL = "Grok部長"


def _keep_inbox() -> bool:
    return os.environ.get("JARVIS_GROK_BUCHO_KEEP_INBOX", "").strip() in ("1", "true", "yes")


def _bucho_label_id(svc) -> str | None:
    labels = svc.users().labels().list(userId="me").execute().get("labels") or []
    for lb in labels:
        if lb.get("name") == BUCHO_LABEL:
            return lb.get("id")
    created = (
        svc.users()
        .labels()
        .create(
            userId="me",
            body={
                "name": BUCHO_LABEL,
                "labelListVisibility": "labelShow",
                "messageListVisibility": "show",
            },
        )
        .execute()
    )
    return created.get("id")


def archive_processed(svc, msg: dict[str, Any], label_id: str | None) -> bool:
    """取込済みの [Grok部長] は自分発信の機械連絡なので受信トレイ・未読から外す（要対応判断に出さない）。"""
    if "INBOX" not in (msg.get("label_ids") or []) and "UNREAD" not in (
        msg.get("label_ids") or []
    ):
        return False
    body: dict[str, Any] = {"removeLabelIds": ["INBOX", "UNREAD"]}
    if label_id:
        body["addLabelIds"] = [label_id]
    svc.users().messages().modify(userId="me", id=msg["id"], body=body).execute()
    return True


def is_scope_error(exc: Exception) -> bool:
    """Gmail API の 403 insufficient scopes（再認可しないと直らない）か。"""
    text = str(exc)
    return "insufficient authentication scopes" in text or "insufficientPermissions" in text


def apply_from_gmail(*, dry_run: bool, days: int, reprocess: bool) -> dict[str, Any]:
    sys.path.insert(0, str(REPO / "scripts"))
    from jarvis_kurashift_vendor_list import (
        apply_marks_from_text,
        merge_vendors_from_text,
        parse_discovery_yaml_from_text,
        parse_mark_commands,
    )

    print("使用アカウント: estate / Gmail API（[Grok部長] 受信取込）")

    svc = gmail_service()
    state = load_state()
    processed = set(state.get("processed_ids") or [])
    messages = fetch_bucho_messages(svc, days=days, max_results=30)

    results: list[dict[str, Any]] = []
    total_marks = 0
    total_applied = 0
    total_discovery_parsed = 0
    total_discovery_added = 0

    archived = 0
    label_id: str | None = None
    if not dry_run and not _keep_inbox():
        try:
            label_id = _bucho_label_id(svc)
        except Exception as e:
            print(f"# grok_bucho label soft-fail: {e}", file=sys.stderr)

    scope_missing = False

    def _archive(msg: dict[str, Any]) -> None:
        nonlocal archived, scope_missing
        if dry_run or _keep_inbox() or scope_missing:
            return
        try:
            if archive_processed(svc, msg, label_id):
                archived += 1
        except Exception as e:
            if is_scope_error(e):
                # 権限不足は全件同じ結果になる。1 回だけ書いて、この回の片付けは止める
                scope_missing = True
                print(
                    "# grok_bucho archive skip: トークンに gmail.modify が無い"
                    "（estate の Gmail トークンを再認可すれば片付けが動く）",
                    file=sys.stderr,
                )
                return
            print(f"# grok_bucho archive soft-fail id={msg.get('id')}: {e}", file=sys.stderr)

    for msg in messages:
        mid = msg["id"]
        if mid in processed and not reprocess:
            # 以前の取込済みで受信トレイに残っているものも片付ける
            _archive(msg)
            continue
        body = msg.get("body") or ""
        cmds = parse_mark_commands(body)
        discovery_preview = parse_discovery_yaml_from_text(body)
        entry: dict[str, Any] = {
            "message_id": mid,
            "subject": msg.get("subject"),
            "parsed_marks": len(cmds),
            "parsed_discovery": len(discovery_preview),
        }
        if cmds:
            out = apply_marks_from_text(body, dry_run=dry_run)
            entry["apply"] = out
            total_marks += out.get("parsed", 0)
            total_applied += out.get("applied", 0)
            entry["ok"] = out.get("ok", False)
        else:
            entry["apply"] = {"ok": True, "skipped": "no --mark in body"}

        if discovery_preview:
            disc = merge_vendors_from_text(body, dry_run=dry_run)
            entry["discovery"] = disc
            total_discovery_parsed += disc.get("parsed", 0)
            total_discovery_added += disc.get("added", 0)
            entry["ok"] = entry.get("ok", True) and disc.get("ok", False)
        else:
            entry["discovery"] = {"ok": True, "skipped": "no discovery yaml"}

        if "ok" not in entry:
            entry["ok"] = True

        results.append(entry)
        if not dry_run:
            processed.add(mid)
            if entry.get("ok"):
                _archive(msg)

    if not dry_run and results:
        state["processed_ids"] = sorted(processed)[-500:]
        save_state(state)

    summary = {
        "ok": True,
        "messages_seen": len(messages),
        "messages_processed": len(results),
        "marks_parsed": total_marks,
        "marks_applied": total_applied,
        "discovery_parsed": total_discovery_parsed,
        "discovery_added": total_discovery_added,
        "dry_run": dry_run,
        "archived": archived,
        "results": results,
    }

    print("📎 Grok部長メール取込")
    print(f"- 対象: 直近{days}日 · subject {BUCHO_PREFIX}")
    print(f"- 処理: {len(results)}通（一覧{len(messages)}通）")
    print(f"- --mark: 解析 {total_marks} 件 · 反映 {total_applied} 件")
    print(
        f"- 探索追記: 解析 {total_discovery_parsed} 件 · 新規追加 {total_discovery_added} 件"
    )
    print(f"- 受信トレイから整理: {archived} 通（ラベル「{BUCHO_LABEL}」・既読）")
    if dry_run:
        print("- モード: dry-run（YAML 未更新）")
    elif not results:
        print("- 新規メールなし（またはすべて処理済み）")
    print(f"BUCHO_MAIL_APPLY:{json.dumps(summary, ensure_ascii=False)}")
    return summary


def _soft_stall_evening_after_marks(marks_applied: int) -> None:
    """S2 --mark 反映後に stall runner（sync + 日次 #report）。失敗しても本処理は止めない。"""
    if marks_applied <= 0:
        return
    if os.environ.get("JARVIS_VENDOR_OUTREACH_STALL_DISABLE", "").strip() in (
        "1",
        "true",
        "yes",
    ):
        return
    stall = REPO / "scripts" / "jarvis_vendor_outreach_stall_runner.py"
    if not stall.is_file():
        return
    py = Path.home() / "selenium_env" / "venv" / "bin" / "python"
    exe = str(py if py.is_file() else sys.executable)
    try:
        r = subprocess.run(
            [exe, str(stall), "--apply", "--evening", "--lane", "all"],
            cwd=str(REPO),
            env=os.environ.copy(),
            capture_output=True,
            text=True,
            timeout=180,
        )
        if r.stdout:
            print(r.stdout.rstrip())
        if r.returncode != 0:
            print(
                f"# vendor_outreach_stall after marks soft-fail rc={r.returncode}",
                file=sys.stderr,
            )
    except Exception as e:
        print(f"# vendor_outreach_stall after marks soft-fail: {e}", file=sys.stderr)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="YAML に反映")
    ap.add_argument("--dry-run", action="store_true", help="プレビューのみ")
    ap.add_argument("--days", type=int, default=14, help="検索日数（既定14）")
    ap.add_argument(
        "--reprocess",
        action="store_true",
        help="処理済み message_id も再実行",
    )
    args = ap.parse_args()

    if not args.apply and not args.dry_run:
        args.dry_run = True

    out = apply_from_gmail(
        dry_run=not args.apply,
        days=args.days,
        reprocess=args.reprocess,
    )
    if args.apply and out.get("ok"):
        _soft_stall_evening_after_marks(int(out.get("marks_applied") or 0))
    return 0 if out.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
