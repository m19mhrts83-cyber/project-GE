#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Todoist コメント入口 — メール本線 + API 巡回保険.

方針（2026-09-21・松野）:
  - **本線**: jarvis@ の Todoist 通知メール（未読）を読む → 対応後に既読
  - **保険**: Todoist API で進行中／オーナー確認の新着コメントを拾う
    （通知漏れ・既読忘れの穴埋め。本線で拾った comment_id は保険で重複しない）

  cd ~/git-repos && set -a && source .env.jarvis_private && set +a
  ~/selenium_env/venv/bin/python scripts/jarvis_todoist_comment_inbox.py
  ~/selenium_env/venv/bin/python scripts/jarvis_todoist_comment_inbox.py --mark-read
  ~/selenium_env/venv/bin/python scripts/jarvis_todoist_comment_inbox.py --mail-only
  ~/selenium_env/venv/bin/python scripts/jarvis_todoist_comment_inbox.py --api-only

既定は報告のみ（既読にしない）。対応が終わったら `--mark-read`。
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
MANUAL = REPO / "215_kamiooya" / "C1_cursor" / "1b_Cursorマニュアル"
TOKEN_GMAIL = MANUAL / "token_jarvis.json"
STATE_PATH = REPO / ".jarvis_state" / "todoist_comment_inbox.json"
YAML_PATH = REPO / "config" / "todoist_projects.yaml"
DEFAULT_API = "https://api.todoist.com/api/v1"
JST = timezone(timedelta(hours=9))

TASK_URL_RE = re.compile(
    r"https://app\.todoist\.com/app/task/([A-Za-z0-9]+)(?:\?[^#\s\"'<>]*)?(?:#comment-([A-Za-z0-9]+))?",
    re.I,
)
SUBJ_COMMENT_RE = re.compile(
    r'[「"“](.+?)[」"”]\s*のタスクにコメント',
)
BODY_STOP_MARKERS = (
    "ブラウザで表示",
    "Todoist logo",
    "新しいコメント",
    "こちらのタスクに新しいコメント",
)
ZERO_WIDTH = re.compile(r"[\u200b-\u200f\u202a-\u202e\ufeff\u00a0]+")


def _now_iso() -> str:
    return datetime.now(JST).isoformat(timespec="seconds")


def _load_state() -> dict[str, Any]:
    if not STATE_PATH.is_file():
        return {
            "processed_gmail_ids": [],
            "api_seen_comment_ids": [],
            "last_mail_run_at": None,
            "last_api_poll_at": None,
        }
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {
            "processed_gmail_ids": [],
            "api_seen_comment_ids": [],
            "last_mail_run_at": None,
            "last_api_poll_at": None,
        }


def _save_state(state: dict[str, Any]) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    # keep lists bounded
    for key in ("processed_gmail_ids", "api_seen_comment_ids"):
        vals = list(state.get(key) or [])
        state[key] = vals[-500:]
    STATE_PATH.write_text(
        json.dumps(state, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _todoist_token() -> str:
    tok = (os.environ.get("TODOIST_API_TOKEN") or "").strip()
    if not tok:
        raise SystemExit("ERROR: TODOIST_API_TOKEN 未設定")
    return tok


def _todoist_req(method: str, path: str, body: dict[str, Any] | None = None) -> Any:
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        f"{DEFAULT_API}{path}",
        data=data,
        headers={
            "Authorization": f"Bearer {_todoist_token()}",
            "Content-Type": "application/json",
        },
        method=method,
    )
    with urllib.request.urlopen(req, timeout=45) as r:
        raw = r.read()
        if not raw:
            return {}
        return json.loads(raw.decode("utf-8"))


def _paginate(path: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    cursor: str | None = None
    while True:
        url = path
        if cursor:
            sep = "&" if "?" in path else "?"
            url = f"{path}{sep}cursor={urllib.parse.quote(cursor)}"
        data = _todoist_req("GET", url)
        if isinstance(data, dict):
            out.extend(data.get("results") or [])
            cursor = data.get("next_cursor")
            if not cursor:
                break
        elif isinstance(data, list):
            out.extend(data)
            break
        else:
            break
    return out


def _load_yaml() -> dict[str, Any]:
    import yaml  # type: ignore

    return yaml.safe_load(YAML_PATH.read_text(encoding="utf-8")) or {}


def _gmail_service():
    sys.path.insert(0, str(MANUAL))
    from gmail_api_scopes import GMAIL_SCOPES_215  # noqa: E402
    from google.auth.transport.requests import Request  # noqa: E402
    from google.oauth2.credentials import Credentials  # noqa: E402
    from googleapiclient.discovery import build  # noqa: E402

    if not TOKEN_GMAIL.is_file():
        raise SystemExit(
            f"ERROR: {TOKEN_GMAIL} がありません。"
            " scripts/jarvis_gmail_jarvis_token_auth.py で発行してください。"
        )
    creds = Credentials.from_authorized_user_file(str(TOKEN_GMAIL), GMAIL_SCOPES_215)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        TOKEN_GMAIL.write_text(creds.to_json(), encoding="utf-8")
    return build("gmail", "v1", credentials=creds, cache_discovery=False)


def _walk_parts(payload: dict[str, Any], out: list[tuple[str, str]]) -> None:
    mt = payload.get("mimeType") or ""
    data = (payload.get("body") or {}).get("data")
    if data and mt in ("text/plain", "text/html"):
        out.append((mt, base64.urlsafe_b64decode(data).decode("utf-8", "replace")))
    for part in payload.get("parts") or []:
        _walk_parts(part, out)


def _clean_text(s: str) -> str:
    s = ZERO_WIDTH.sub("", s)
    s = s.replace("\r\n", "\n").replace("\r", "\n")
    return s.strip()


def _parse_mail(full: dict[str, Any]) -> dict[str, Any]:
    headers = {
        (h.get("name") or "").lower(): (h.get("value") or "")
        for h in (full.get("payload") or {}).get("headers") or []
    }
    subject = headers.get("subject", "")
    parts: list[tuple[str, str]] = []
    _walk_parts(full.get("payload") or {}, parts)
    plain = next((b for mt, b in parts if mt == "text/plain"), "")
    html = next((b for mt, b in parts if mt == "text/html"), "")
    blob = plain or html
    task_id = ""
    comment_id = ""
    for src in (plain, html, blob):
        m = TASK_URL_RE.search(src)
        if m:
            task_id = m.group(1)
            comment_id = m.group(2) or ""
            break
    title = ""
    sm = SUBJ_COMMENT_RE.search(subject)
    if sm:
        title = sm.group(1).strip()
    # comment body: plain lines after the first (notification header)
    comment_text = ""
    if plain:
        lines = [ln.strip() for ln in _clean_text(plain).split("\n") if ln.strip()]
        body_lines = []
        for ln in lines[1:]:
            if any(m in ln for m in BODY_STOP_MARKERS):
                break
            if ln.startswith("http") and "todoist" in ln.lower():
                continue
            if ln.startswith("[http"):
                continue
            if len(ln) > 400 and "http" in ln:
                continue
            body_lines.append(ln)
            if len("\n".join(body_lines)) > 600:
                break
        comment_text = "\n".join(body_lines).strip()
    if not comment_text:
        comment_text = _clean_text(full.get("snippet") or "")[:400]

    kind = "comment"
    if "コメント" not in subject and "comment" not in subject.lower():
        kind = "other_notify"

    posted = ""
    date_h = headers.get("date") or ""
    if date_h:
        try:
            posted = parsedate_to_datetime(date_h).astimezone(JST).isoformat(timespec="seconds")
        except Exception:
            posted = date_h

    return {
        "gmail_id": full.get("id") or "",
        "subject": subject,
        "title": title,
        "task_id": task_id,
        "comment_id": comment_id,
        "comment_text": comment_text,
        "kind": kind,
        "posted_at": posted,
        "unread": "UNREAD" in (full.get("labelIds") or []),
        "source": "mail",
    }


def fetch_unread_todoist_mail(*, max_results: int = 30) -> list[dict[str, Any]]:
    svc = _gmail_service()
    q = "from:todoist.com is:unread"
    res = (
        svc.users()
        .messages()
        .list(userId="me", q=q, maxResults=max_results)
        .execute()
    )
    items: list[dict[str, Any]] = []
    for m in res.get("messages") or []:
        full = (
            svc.users()
            .messages()
            .get(userId="me", id=m["id"], format="full")
            .execute()
        )
        items.append(_parse_mail(full))
    return items


def mark_gmail_read(gmail_ids: list[str]) -> int:
    if not gmail_ids:
        return 0
    svc = _gmail_service()
    n = 0
    for gid in gmail_ids:
        svc.users().messages().modify(
            userId="me",
            id=gid,
            body={"removeLabelIds": ["UNREAD"]},
        ).execute()
        n += 1
    return n


def _section_focus(cfg: dict[str, Any]) -> dict[str, set[str]]:
    """project_id -> set of section_ids for 進行中/オーナー確認."""
    focus: dict[str, set[str]] = {}
    projects = cfg.get("projects") or {}
    for _key, proj in projects.items():
        if not isinstance(proj, dict):
            continue
        pid = str(proj.get("project_id") or "").strip()
        if not pid:
            continue
        sids = proj.get("section_ids") or {}
        wanted = set()
        for name in ("進行中", "オーナー確認"):
            sid = sids.get(name)
            if sid:
                wanted.add(str(sid))
        if wanted:
            focus[pid] = wanted
    return focus


def fetch_api_insurance(
    *,
    state: dict[str, Any],
    mail_comment_ids: set[str],
    newer_than_hours: int = 48,
) -> list[dict[str, Any]]:
    cfg = _load_yaml()
    focus = _section_focus(cfg)
    if not focus:
        return []

    seen = set(state.get("api_seen_comment_ids") or [])
    cutoff = datetime.now(timezone.utc) - timedelta(hours=newer_than_hours)
    out: list[dict[str, Any]] = []

    for pid, section_ids in focus.items():
        tasks = _paginate(f"/tasks?project_id={urllib.parse.quote(pid)}")
        for t in tasks:
            if str(t.get("section_id") or "") not in section_ids:
                continue
            tid = str(t.get("id") or "")
            if not tid:
                continue
            try:
                comments = _paginate(f"/comments?task_id={urllib.parse.quote(tid)}")
            except Exception:
                continue
            for c in comments:
                cid = str(c.get("id") or "")
                if not cid or cid in seen or cid in mail_comment_ids:
                    continue
                posted_raw = c.get("posted_at") or c.get("posted") or ""
                try:
                    pdt = datetime.fromisoformat(
                        str(posted_raw).replace("Z", "+00:00")
                    )
                    if pdt.tzinfo is None:
                        pdt = pdt.replace(tzinfo=timezone.utc)
                    if pdt < cutoff:
                        continue
                except Exception:
                    pass
                content = (c.get("content") or "").strip()
                # Jarvis 自身の定型コメントは保険対象外（ノイズ低減）
                if content.startswith("サマリ:") or content.startswith("タスク完了したよ"):
                    continue
                out.append(
                    {
                        "gmail_id": "",
                        "subject": "",
                        "title": t.get("content") or "",
                        "task_id": tid,
                        "comment_id": cid,
                        "comment_text": content[:800],
                        "kind": "comment",
                        "posted_at": posted_raw,
                        "unread": None,
                        "source": "api",
                    }
                )
    return out


def _print_report(items: list[dict[str, Any]], *, marked: int) -> None:
    mail_n = sum(1 for x in items if x.get("source") == "mail")
    api_n = sum(1 for x in items if x.get("source") == "api")
    print("📎 Todoistコメント入口（メール本線＋API保険）")
    print(f"- 未読メール: {mail_n}件 / API保険の追加: {api_n}件 / 既読化: {marked}")
    if not items:
        print("- 新規なし")
        return
    for i, it in enumerate(items, 1):
        src = it.get("source")
        print(f"{i}. [{src}] {it.get('title') or '(タイトル不明)'}")
        print(f"   task_id={it.get('task_id') or '-'} comment_id={it.get('comment_id') or '-'}")
        if it.get("gmail_id"):
            print(f"   gmail_id={it['gmail_id']}")
        text = (it.get("comment_text") or "").replace("\n", " / ")
        if len(text) > 200:
            text = text[:200] + "…"
        print(f"   本文: {text}")
    print("- 対応後: `--mark-read` で未読メールを既読に（API保険分は state に記録）")


def main() -> int:
    ap = argparse.ArgumentParser(description="Todoist コメント入口（メール本線＋API保険）")
    ap.add_argument("--mail-only", action="store_true", help="メール本線のみ")
    ap.add_argument("--api-only", action="store_true", help="API保険のみ")
    ap.add_argument(
        "--mark-read",
        action="store_true",
        help="今回拾った未読メールを既読にし、API comment_id を state に記録",
    )
    ap.add_argument("--max-mail", type=int, default=30)
    ap.add_argument("--api-hours", type=int, default=48, help="API保険の遡及時間")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    do_mail = not args.api_only
    do_api = not args.mail_only
    state = _load_state()
    items: list[dict[str, Any]] = []
    mail_comment_ids: set[str] = set()

    if do_mail:
        try:
            mails = fetch_unread_todoist_mail(max_results=args.max_mail)
        except SystemExit:
            raise
        except Exception as e:
            print(f"ERROR: Gmail 読取失敗: {e}", file=sys.stderr)
            return 1
        for m in mails:
            if m.get("comment_id"):
                mail_comment_ids.add(str(m["comment_id"]))
            items.append(m)
        state["last_mail_run_at"] = _now_iso()

    if do_api:
        try:
            extras = fetch_api_insurance(
                state=state,
                mail_comment_ids=mail_comment_ids,
                newer_than_hours=args.api_hours,
            )
            items.extend(extras)
            state["last_api_poll_at"] = _now_iso()
        except SystemExit:
            raise
        except Exception as e:
            print(f"WARNING: API保険失敗（メール本線は継続）: {e}", file=sys.stderr)

    marked = 0
    if args.mark_read:
        gids = [x["gmail_id"] for x in items if x.get("source") == "mail" and x.get("gmail_id")]
        try:
            marked = mark_gmail_read(gids)
        except Exception as e:
            print(f"ERROR: 既読化失敗: {e}", file=sys.stderr)
            return 1
        proc = list(state.get("processed_gmail_ids") or [])
        proc.extend(gids)
        state["processed_gmail_ids"] = proc
        seen = list(state.get("api_seen_comment_ids") or [])
        for x in items:
            cid = x.get("comment_id")
            if cid:
                seen.append(str(cid))
        state["api_seen_comment_ids"] = seen
        _save_state(state)
    else:
        # still refresh run timestamps without consuming
        _save_state(state)

    if args.json:
        print(
            json.dumps(
                {"ok": True, "items": items, "marked_read": marked},
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        _print_report(items, marked=marked)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except urllib.error.HTTPError as e:
        print(f"ERROR: HTTP {e.code}: {e.read()[:300]!r}", file=sys.stderr)
        raise SystemExit(1)
