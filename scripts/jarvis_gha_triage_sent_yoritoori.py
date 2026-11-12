#!/usr/bin/env python3
"""
GHA / クラウド: Slack・ダッシュボードから送った返信（triage_items status=sent）を
OneDrive `5.やり取り.md` に「自分から送信」として追記する（Graph 書込）。

2026-11-13 追加: これまで送信分の記録は Mac 側（gmail_to_yoritoori の送信トレイ取込／
jarvis_triage_yoritoori_catchup）だけで、Mac が動かない日は記録が遅れていた。
クラウドの Gmail 取込は admin の受信しか見ないため、estate から送った Slack 返信は拾えない。
送信本文は triage_items.draft_text（送信時に送った本文で上書き）にあるので、それを使う。

重複防止:
  - payload.yoritoori_appended が立っていれば何もしない（Mac catchup と同じ目印）
  - md に同じ（相手・件名・日付）の「自分から送信」ブロックがあれば目印だけ立てる
    （gmail_to_yoritoori の送信トレイ取込と同じキー。こちらが先に書けば向こうも重複扱いになる）

  python scripts/jarvis_gha_triage_sent_yoritoori.py            # dry-run
  python scripts/jarvis_gha_triage_sent_yoritoori.py --apply
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

JST = ZoneInfo("Asia/Tokyo")
REPO = Path(__file__).resolve().parents[1]
MANUAL = REPO / "215_kamiooya" / "C1_cursor" / "1b_Cursorマニュアル"
sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, str(MANUAL))

from jarvis_gha_partner_gmail_yoritoori import already_in_md, yoritoori_rel  # noqa: E402


def parse_iso(s: str) -> datetime | None:
    s = (s or "").strip()
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def reply_subject(subject: str) -> str:
    s = (subject or "").strip() or "（件名なし）"
    return s if s.lower().startswith("re:") else f"Re: {s}"


def build_sent_block(*, partner_name: str, date_str: str, subject: str, body: str,
                     attachments: list[str] | None = None) -> str:
    from yoritoori_utils import make_summary  # type: ignore

    summary = make_summary(body)
    subject_block = f"**件名**: {subject}\n" if subject else ""
    attach_block = ""
    if attachments:
        attach_block = "\n**添付ファイル**: " + ", ".join(attachments) + "\n"
    return f"""

### {date_str}｜{partner_name}｜自分から送信｜{summary}

{subject_block}{body}{attach_block}

---
"""


def append_sent(old: str, block: str) -> str:
    from yoritoori_utils import insert_after_timeline_heading  # type: ignore

    return insert_after_timeline_heading(old, block)


def pick_rows(rows: list[dict[str, Any]], *, since: datetime) -> list[dict[str, Any]]:
    """追記対象: 送信済み・本文あり・フォルダあり・未追記・期間内。"""
    out = []
    for it in rows:
        payload = it.get("payload") if isinstance(it.get("payload"), dict) else {}
        if payload.get("yoritoori_appended"):
            continue
        if not (it.get("folder") or "").strip():
            continue
        if not (it.get("draft_text") or "").strip():
            continue
        sent_at = parse_iso(str(payload.get("sent_at") or ""))
        if not sent_at or sent_at < since:
            continue
        out.append(it)
    return out


def run(*, dry_run: bool, days: int, limit: int) -> dict[str, int]:
    from supabase import create_client
    from jarvis_onedrive_graph import append_text_graph, graph_configured, read_file

    stats = {"scanned": 0, "appended": 0, "dup": 0, "fail": 0, "dry_run": 0}
    url = (os.environ.get("JARVIS_SUPABASE_URL") or "").strip()
    key = (
        os.environ.get("JARVIS_SUPABASE_SERVICE_ROLE_KEY")
        or os.environ.get("JARVIS_SUPABASE_SECRET_KEY")
        or ""
    ).strip()
    if not url or not key:
        raise SystemExit("JARVIS_SUPABASE_* 未設定")
    if not graph_configured():
        raise SystemExit("MS_GRAPH_* 未設定（OneDrive に書けない）")

    sb = create_client(url, key)
    res = (
        sb.table("triage_items")
        .select("id,partner,folder,subject,draft_text,payload,status,kind")
        .eq("status", "sent")
        .neq("kind", "activity")
        .order("updated_at", desc=True)
        .limit(limit)
        .execute()
    )
    since = datetime.now(timezone.utc) - timedelta(days=max(1, days))
    rows = pick_rows(res.data or [], since=since)
    stats["scanned"] = len(rows)

    for it in rows:
        payload = dict(it.get("payload") or {})
        folder = it["folder"].strip()
        partner = (it.get("partner") or folder).strip()
        subject = reply_subject(str(it.get("subject") or ""))
        body = str(it.get("draft_text") or "").strip()
        sent_at = parse_iso(str(payload.get("sent_at")))
        assert sent_at is not None
        sent_jst = sent_at.astimezone(JST)
        date_str = sent_jst.strftime("%Y/%m/%d %H:%M")
        date_key = sent_jst.strftime("%Y-%m-%d")
        rel = yoritoori_rel(folder)
        try:
            text = read_file("onedrive", rel).decode("utf-8", errors="replace")
        except Exception as e:
            print(f"# read fail {it['id']} {rel}: {e}", file=sys.stderr)
            stats["fail"] += 1
            continue

        dup = already_in_md(text, partner, subject, date_key)
        if dry_run:
            print(f"# dry-run {'dup' if dup else 'append'} {folder} {subject[:40]}")
            stats["dup" if dup else "dry_run"] += 1
            continue

        if not dup:
            block = build_sent_block(
                partner_name=partner,
                date_str=date_str,
                subject=subject,
                body=body,
                attachments=[str(x) for x in payload.get("sent_attachments") or []],
            )

            def transform(old: str, _b: str, block: str = block) -> str:
                # 書く直前にもう一度見る（Mac 側と同時に走っても二重にしない）
                if already_in_md(old, partner, subject, date_key):
                    return old
                return append_sent(old, block)

            try:
                append_text_graph(rel, "", transform=transform)
            except Exception as e:
                print(f"# write fail {it['id']} {rel}: {e}", file=sys.stderr)
                stats["fail"] += 1
                continue
            stats["appended"] += 1
            print(f"# appended {folder} {subject[:40]}")
        else:
            stats["dup"] += 1

        payload["yoritoori_appended"] = True
        payload["yoritoori_appended_at"] = datetime.now(JST).isoformat(timespec="seconds")
        payload["yoritoori_appended_by"] = "gha" if not dup else "gha_seen"
        sb.table("triage_items").update({"payload": payload}).eq("id", it["id"]).execute()

    return stats


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="書込を実行（既定は dry-run）")
    ap.add_argument("--days", type=int, default=7, help="送信日がこの日数以内の行だけ")
    ap.add_argument("--limit", type=int, default=80)
    args = ap.parse_args(argv)
    stats = run(dry_run=not args.apply, days=args.days, limit=args.limit)
    print(f"📤 sent→md: {stats}")
    return 0 if stats.get("fail", 0) == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
