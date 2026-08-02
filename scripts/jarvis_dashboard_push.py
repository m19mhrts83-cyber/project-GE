#!/usr/bin/env python3
"""
Jarvis: ローカル queue / situation_watch を jarvis-dashboard（Supabase）へ upsert。

  cd ~/git-repos && set -a && source .env.jarvis_private && set +a
  python scripts/jarvis_dashboard_push.py
  python scripts/jarvis_dashboard_push.py --triage-only
  python scripts/jarvis_dashboard_push.py --watch-only

要: JARVIS_SUPABASE_URL + JARVIS_SUPABASE_SERVICE_ROLE_KEY
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from supabase import create_client

JST = ZoneInfo("Asia/Tokyo")
REPO = Path(__file__).resolve().parents[1]
STATE = REPO / ".jarvis_state"
QUEUE_PATH = STATE / "night_triage" / "queue.json"
WATCH_PATH = STATE / "situation_watch.json"
WATCH_SCRIPT = REPO / "scripts" / "jarvis_situation_watch.py"


def now_iso() -> str:
    return datetime.now(JST).strftime("%Y-%m-%dT%H:%M:%S%z")


def client():
    url = (os.environ.get("JARVIS_SUPABASE_URL") or "").strip()
    key = (os.environ.get("JARVIS_SUPABASE_SERVICE_ROLE_KEY") or "").strip()
    if not url or not key:
        raise SystemExit(
            "JARVIS_SUPABASE_URL / JARVIS_SUPABASE_SERVICE_ROLE_KEY が未設定です。"
            " .env.jarvis_private に追記してください（service_role は Dashboard → API）。"
        )
    return create_client(url, key)


def refresh_watch() -> None:
    py = Path.home() / "selenium_env" / "venv" / "bin" / "python"
    import subprocess

    exe = str(py) if py.is_file() else sys.executable
    subprocess.run([exe, str(WATCH_SCRIPT)], cwd=str(REPO), check=False, timeout=60)


def push_triage(sb) -> int:
    if not QUEUE_PATH.is_file():
        print("# triage: queue.json なし", file=sys.stderr)
        return 0
    data = json.loads(QUEUE_PATH.read_text(encoding="utf-8"))
    items = data.get("items") or []
    # Web で閉じた行（sent/skipped/snoozed/done）を Mac push で pending に戻さない。
    # Web で保存した draft_text / payload メタも潰さない。
    PROTECTED = {"sent", "skipped", "snoozed", "done"}
    KEEP_PAYLOAD = (
        "sent_at",
        "gmail_sent_id",
        "gmail_sent_thread_id",
        "yoritoori_appended",
        "yoritoori_appended_at",
        "web_draft_saved_at",
    )
    remote_by_id: dict[str, dict[str, Any]] = {}
    ids = [str(it.get("id") or "").strip() for it in items if str(it.get("id") or "").strip()]
    try:
        for i in range(0, len(ids), 80):
            chunk_ids = ids[i : i + 80]
            r = (
                sb.table("triage_items")
                .select("id,status,draft_text,payload,updated_at")
                .in_("id", chunk_ids)
                .execute()
            )
            for x in r.data or []:
                remote_by_id[str(x["id"])] = x
    except Exception as e:
        print(f"# triage protected merge skipped: {e}", file=sys.stderr)
    rows: list[dict[str, Any]] = []
    for it in items:
        iid = str(it.get("id") or "").strip()
        if not iid:
            continue
        st = it.get("status") or "pending"
        remote = remote_by_id.get(iid) or {}
        remote_st = str(remote.get("status") or "")
        if st == "pending" and remote_st in PROTECTED:
            st = remote_st
        payload = {
            k: it.get(k)
            for k in (
                "reason",
                "draft_gemini",
                "draft_cursor",
                "message_id_header",
                "engine",
            )
            if it.get(k) is not None
        }
        remote_payload = remote.get("payload") if isinstance(remote.get("payload"), dict) else {}
        for k in KEEP_PAYLOAD:
            if remote_payload.get(k) is not None:
                payload[k] = remote_payload[k]
        draft_text = it.get("draft_text") or None
        if remote_payload.get("web_draft_saved_at") and remote.get("draft_text"):
            draft_text = remote.get("draft_text")
        rows.append(
            {
                "id": iid,
                "lane": it.get("lane") or "partner",
                "kind": it.get("kind") or "mail",
                "status": st,
                "partner": it.get("partner") or None,
                "folder": it.get("folder") or None,
                "subject": it.get("subject") or None,
                "received_at": it.get("received_at") or None,
                "summary": it.get("summary") or None,
                "draft_text": draft_text,
                "original_body": (str(it.get("original_body") or ""))[:8000] or None,
                "priority": it.get("priority") or None,
                "channel": it.get("channel") or None,
                "account": it.get("account") or None,
                "gmail_thread_id": it.get("gmail_thread_id") or None,
                "gmail_message_id": it.get("gmail_message_id") or None,
                "from_email": it.get("from_email") or None,
                "seq": it.get("seq"),
                "payload": payload,
                "updated_at": it.get("updated_at") or now_iso(),
            }
        )
    if not rows:
        print("# triage: 0 rows", file=sys.stderr)
        return 0
    # chunk upsert
    n = 0
    for i in range(0, len(rows), 50):
        chunk = rows[i : i + 50]
        sb.table("triage_items").upsert(chunk, on_conflict="id").execute()
        n += len(chunk)
    sb.table("sync_meta").upsert(
        {"key": "triage_pushed_at", "value": now_iso(), "updated_at": now_iso()},
        on_conflict="key",
    ).execute()
    sb.table("sync_meta").upsert(
        [
            {"key": "mac_triage_pushed_at", "value": now_iso(), "updated_at": now_iso()},
            {"key": "triage_source", "value": "mac", "updated_at": now_iso()},
        ],
        on_conflict="key",
    ).execute()
    print(f"# triage upserted {n}", file=sys.stderr)
    return n


def push_watch(sb) -> int:
    refresh_watch()
    if not WATCH_PATH.is_file():
        print("# watch: situation_watch.json なし", file=sys.stderr)
        return 0
    data = json.loads(WATCH_PATH.read_text(encoding="utf-8"))
    items = data.get("items") or []
    # Web アーカイブを Mac push で潰さない（ローカル archived は優先）
    # never_archive / recent_fixes の確認状態は remote を優先マージ
    remote_by_id: dict[str, Any] = {}
    try:
        r = (
            sb.table("watch_status")
            .select("id,status,archived_at,payload")
            .execute()
        )
        remote_by_id = {x["id"]: x for x in (r.data or [])}
    except Exception as e:
        print(f"# watch remote merge skipped: {e}", file=sys.stderr)
    rows = []
    for it in items:
        iid = str(it.get("id") or "").strip()
        if not iid:
            continue
        payload = it.get("payload") if isinstance(it.get("payload"), dict) else {}
        payload = dict(payload)
        remote = remote_by_id.get(iid) or {}
        remote_pl = remote.get("payload") if isinstance(remote.get("payload"), dict) else {}
        never_archive = bool(payload.get("never_archive") or remote_pl.get("never_archive"))
        if never_archive:
            payload["never_archive"] = True

        # merge confirm statuses from remote recent_fixes
        local_fixes = list(payload.get("recent_fixes") or [])
        remote_fixes = list(remote_pl.get("recent_fixes") or [])
        remote_status = {
            str(f.get("id")): f
            for f in remote_fixes
            if isinstance(f, dict) and f.get("id")
        }
        merged_fixes = []
        seen_ids: set[str] = set()
        for f in local_fixes:
            if not isinstance(f, dict):
                continue
            fid = str(f.get("id") or "")
            row = dict(f)
            if fid and fid in remote_status:
                rs = remote_status[fid]
                if rs.get("status") in ("confirmed", "disputed"):
                    row["status"] = rs.get("status")
                    if rs.get("confirmed_at"):
                        row["confirmed_at"] = rs.get("confirmed_at")
            merged_fixes.append(row)
            if fid:
                seen_ids.add(fid)
        for fid, rf in remote_status.items():
            if fid not in seen_ids and rf.get("status") in ("confirmed", "disputed"):
                merged_fixes.append(rf)
        if merged_fixes:
            payload["recent_fixes"] = merged_fixes[-40:]
            payload["pending_confirm_count"] = sum(
                1
                for f in merged_fixes
                if isinstance(f, dict) and f.get("status") == "pending_confirm"
            )
            # ローカル changelog にも確認状態を反映（再適用・pending 表示のずれ防止）
            try:
                cl_path = STATE / "zaim_watch_changelog.json"
                if cl_path.is_file():
                    cl = json.loads(cl_path.read_text(encoding="utf-8"))
                    by_id = {
                        str(f.get("id")): f
                        for f in merged_fixes
                        if isinstance(f, dict) and f.get("id")
                    }
                    changed = False
                    for e in cl.get("entries") or []:
                        fid = str(e.get("id") or "")
                        if fid in by_id and by_id[fid].get("status") in (
                            "confirmed",
                            "disputed",
                        ):
                            if e.get("status") != by_id[fid].get("status"):
                                e["status"] = by_id[fid].get("status")
                                if by_id[fid].get("confirmed_at"):
                                    e["confirmed_at"] = by_id[fid].get("confirmed_at")
                                changed = True
                    if changed:
                        cl["updated_at"] = now_iso()
                        cl_path.write_text(
                            json.dumps(cl, ensure_ascii=False, indent=2) + "\n",
                            encoding="utf-8",
                        )
            except Exception as e:
                print(f"# changelog sync skipped: {e}", file=sys.stderr)

        # ETC: ダッシュボードの「確認しました」を Mac push で潰さない
        if iid == "etc_mileage":
            remote_ack = remote_pl.get("dashboard_ack_target_month")
            local_ack = payload.get("dashboard_ack_target_month")
            ack = remote_ack or local_ack
            if ack:
                payload["dashboard_ack_target_month"] = ack
            rs = payload.get("rebate_summary") if isinstance(payload.get("rebate_summary"), dict) else {}
            target = rs.get("target_month")
            payload["show_banner"] = bool(
                target and rs.get("rebate_yen") is not None and ack != target
            )
            # Mac state にも ack を寄せる（次回 eval 用）
            try:
                etc_path = STATE / "etc_monthly.json"
                if etc_path.is_file() and ack:
                    etc = json.loads(etc_path.read_text(encoding="utf-8"))
                    if etc.get("dashboard_ack_target_month") != ack:
                        etc["dashboard_ack_target_month"] = ack
                        etc_path.write_text(
                            json.dumps(etc, ensure_ascii=False, indent=2) + "\n",
                            encoding="utf-8",
                        )
            except Exception as e:
                print(f"# etc ack sync skipped: {e}", file=sys.stderr)

        st = it.get("status") or "active"
        arch_at = it.get("archived_at")
        if never_archive:
            st = "active"
            arch_at = None
        elif st != "archived" and remote.get("status") == "archived":
            st = "archived"
            arch_at = remote.get("archived_at")
        rows.append(
            {
                "id": iid,
                "title": it.get("title") or iid,
                "category": it.get("category") or None,
                "level": it.get("level") or "info",
                "summary": it.get("summary") or None,
                "detail": it.get("detail") or None,
                "source": it.get("source") or None,
                "cursor_prompt": it.get("cursor_prompt") or None,
                "status": st,
                "archived_at": arch_at,
                "checked_at": it.get("checked_at"),
                "payload": payload,
                "updated_at": now_iso(),
            }
        )
    if not rows:
        return 0
    sb.table("watch_status").upsert(rows, on_conflict="id").execute()
    sb.table("sync_meta").upsert(
        [
            {"key": "watch_pushed_at", "value": now_iso(), "updated_at": now_iso()},
            {"key": "watch_source", "value": "mac", "updated_at": now_iso()},
        ],
        on_conflict="key",
    ).execute()
    print(f"# watch upserted {len(rows)}", file=sys.stderr)
    return len(rows)


def push_other_mail_digest(sb=None) -> int:
    """パートナー以外メールのダイジェストを sync_meta へ。失敗しても 0。"""
    import subprocess

    py = Path.home() / "selenium_env" / "venv" / "bin" / "python"
    exe = str(py) if py.is_file() else sys.executable
    try:
        r = subprocess.run(
            [exe, str(REPO / "scripts" / "jarvis_other_mail_digest.py"), "--push"],
            cwd=str(REPO),
            capture_output=True,
            text=True,
            timeout=120,
            env=os.environ.copy(),
        )
        print(r.stderr or "", file=sys.stderr, end="")
        if r.returncode == 0:
            return 1
        print(f"# other_mail_digest failed rc={r.returncode}", file=sys.stderr)
    except Exception as e:
        print(f"# other_mail_digest failed: {e}", file=sys.stderr)
    return 0


def push_openchat_digest() -> int:
    """815 オプチャ有益ダイジェスト。失敗しても 0。"""
    import subprocess

    py = Path.home() / "selenium_env" / "venv" / "bin" / "python"
    exe = str(py) if py.is_file() else sys.executable
    try:
        r = subprocess.run(
            [exe, str(REPO / "scripts" / "jarvis_openchat_digest.py"), "--push"],
            cwd=str(REPO),
            capture_output=True,
            text=True,
            timeout=180,
            env=os.environ.copy(),
        )
        print(r.stderr or "", file=sys.stderr, end="")
        print(r.stdout or "", file=sys.stderr, end="")
        if r.returncode == 0:
            return 1
        print(f"# openchat_digest failed rc={r.returncode}", file=sys.stderr)
    except Exception as e:
        print(f"# openchat_digest failed: {e}", file=sys.stderr)
    return 0


def push_lanes_finance_subscriptions() -> tuple[int, int, int, int]:
    """サブプロセスで lanes / finance / subscriptions / occupancy を集約＋push。失敗しても 0。"""
    import subprocess

    py = Path.home() / "selenium_env" / "venv" / "bin" / "python"
    exe = str(py) if py.is_file() else sys.executable
    cards_n = fin_n = sub_n = occ_n = 0
    try:
        # 機械的大量カードは出さない。要約確認テーマのみ push
        r = subprocess.run(
            [exe, str(REPO / "scripts" / "jarvis_lane_digest.py"), "--push"],
            cwd=str(REPO),
            capture_output=True,
            text=True,
            timeout=180,
        )
        print(r.stderr or "", file=sys.stderr, end="")
        if r.returncode == 0:
            cards_n = 1
    except Exception as e:
        print(f"# lane digest push failed: {e}", file=sys.stderr)
    try:
        r = subprocess.run(
            [exe, str(REPO / "scripts" / "jarvis_lane_log_flush.py")],
            cwd=str(REPO),
            capture_output=True,
            text=True,
            timeout=60,
        )
        print(r.stderr or "", file=sys.stderr, end="")
        print(r.stdout or "", file=sys.stderr, end="")
    except Exception as e:
        print(f"# lane log flush failed: {e}", file=sys.stderr)
    try:
        r = subprocess.run(
            [exe, str(REPO / "scripts" / "jarvis_finance_metrics.py"), "--push"],
            cwd=str(REPO),
            capture_output=True,
            text=True,
            timeout=120,
        )
        print(r.stderr or "", file=sys.stderr, end="")
        if r.returncode == 0:
            fin_n = 1
    except Exception as e:
        print(f"# finance push failed: {e}", file=sys.stderr)
    try:
        r = subprocess.run(
            [exe, str(REPO / "scripts" / "jarvis_subscriptions_push.py"), "--push"],
            cwd=str(REPO),
            capture_output=True,
            text=True,
            timeout=60,
        )
        print(r.stderr or "", file=sys.stderr, end="")
        if r.returncode == 0:
            sub_n = 1
    except Exception as e:
        print(f"# subscriptions push failed: {e}", file=sys.stderr)
    try:
        r = subprocess.run(
            [
                exe,
                str(REPO / "scripts" / "jarvis_property_occupancy_from_mail.py"),
                "--push",
            ],
            cwd=str(REPO),
            capture_output=True,
            text=True,
            timeout=120,
        )
        print(r.stderr or "", file=sys.stderr, end="")
        if r.returncode == 0:
            occ_n = 1
            print(r.stdout or "", file=sys.stderr, end="")
    except Exception as e:
        print(f"# occupancy mail failed: {e}", file=sys.stderr)
    return cards_n, fin_n, sub_n, occ_n


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--triage-only", action="store_true")
    ap.add_argument("--watch-only", action="store_true")
    ap.add_argument("--full", action="store_true", help="lanes/finance/subscriptions も含めて push")
    args = ap.parse_args(argv)

    sb = client()
    t = w = digest = oc_digest = 0
    if not args.watch_only:
        t = push_triage(sb)
        digest = push_other_mail_digest(sb)
        oc_digest = push_openchat_digest()
    if not args.triage_only:
        w = push_watch(sb)
    cards = finance = subscriptions = occupancy = 0
    if args.full or (not args.triage_only and not args.watch_only):
        cards, finance, subscriptions, occupancy = push_lanes_finance_subscriptions()
    print(
        json.dumps(
            {
                "triage": t,
                "watch": w,
                "other_mail_digest": digest,
                "openchat_digest": oc_digest,
                "lanes": cards,
                "finance": finance,
                "subscriptions": subscriptions,
                "occupancy_mail": occupancy,
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())