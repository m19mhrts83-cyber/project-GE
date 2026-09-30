#!/usr/bin/env python3
"""
ダッシュボードからキューされた Zaim 費目変更を Mac 側で適用する。

  cd ~/git-repos && set -a && source .env.jarvis_private && set +a
  python scripts/jarvis_zaim_dashboard_apply.py
  python scripts/jarvis_zaim_dashboard_apply.py --dry-run

Supabase watch_status.payload.pending_category_applies を読み、
Playwright で Zaim に set_category を適用し、学習ルールを更新する。
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

JST = ZoneInfo("Asia/Tokyo")
REPO = Path(__file__).resolve().parents[1]
STATE = REPO / ".jarvis_state"
WATCH_ID = "zaim_quality"
CHANGELOG_PATH = STATE / "zaim_watch_changelog.json"
PY = Path.home() / "selenium_env" / "venv" / "bin" / "python"
EXE = str(PY) if PY.is_file() else sys.executable
LOG_DIR = Path.home() / "Library" / "Logs" / "jarvis_zaim"
# CSV 週次・銀行同期（jarvis_zaim_bank_sync_manual）と同じ Playwright 共有ロック。
# 同時に Playwright を走らせると Zaim セッションを壊すため、必ず共有ロックを取る。
PLAYWRIGHT_LOCK = LOG_DIR / "zaim_playwright.lock"

sys.path.insert(0, str(Path(__file__).resolve().parent))
import jarvis_zaim_learn as zlearn  # noqa: E402
import jarvis_zaim_watch_runner as zrunner  # noqa: E402


def now_iso() -> str:
    return datetime.now(JST).strftime("%Y-%m-%dT%H:%M:%S%z")


def acquire_playwright_lock(*, wait_sec: int = 0) -> bool:
    """mkdir ロック。CSV 週次・銀行同期と共有。取得できなければ False。"""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    deadline = time.time() + max(0, wait_sec)
    while True:
        try:
            os.mkdir(PLAYWRIGHT_LOCK)
            (PLAYWRIGHT_LOCK / "owner.txt").write_text(
                f"dashboard_apply pid={os.getpid()} at={now_iso()}\n",
                encoding="utf-8",
            )
            return True
        except FileExistsError:
            if time.time() >= deadline:
                return False
            time.sleep(2)


def release_playwright_lock() -> None:
    try:
        for p in PLAYWRIGHT_LOCK.iterdir():
            p.unlink(missing_ok=True)
    except Exception:
        pass
    try:
        PLAYWRIGHT_LOCK.rmdir()
    except Exception:
        pass


def supabase_client():
    from supabase import create_client

    url = (os.environ.get("JARVIS_SUPABASE_URL") or "").strip()
    key = (os.environ.get("JARVIS_SUPABASE_SERVICE_ROLE_KEY") or "").strip()
    if not url or not key:
        raise SystemExit(
            "JARVIS_SUPABASE_URL / JARVIS_SUPABASE_SERVICE_ROLE_KEY が未設定です。"
        )
    return create_client(url, key)


def load_changelog() -> dict[str, Any]:
    if CHANGELOG_PATH.is_file():
        try:
            return json.loads(CHANGELOG_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"updated_at": None, "entries": []}


def save_changelog(data: dict[str, Any]) -> None:
    CHANGELOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    data["updated_at"] = now_iso()
    CHANGELOG_PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def pending_to_action(p: dict[str, Any]) -> dict[str, Any]:
    return {
        "action": "set_category",
        "target": "category",
        "value": p.get("category"),
        "genre": p.get("genre") or "",
        "date": p.get("date"),
        "shop": p.get("shop"),
        "item": p.get("item"),
        "amount": p.get("amount"),
        "pay": p.get("pay"),
        "method": p.get("method") or "payment",
        "learn_key": p.get("learn_key"),
        "row_key": p.get("row_key"),
        "suggest": p.get("category"),
        "confidence": "dashboard",
    }


def learn_from_apply(p: dict[str, Any], *, ok: bool) -> None:
    if not ok:
        return
    key = str(p.get("learn_key") or "").strip()
    if not key:
        key = zlearn.learn_key(
            str(p.get("shop") or ""), str(p.get("item") or "")
        )
    cat = str(p.get("category") or "").strip()
    gen = str(p.get("genre") or "").strip()
    if not key or not cat:
        return
    rules = zlearn.load_rules()
    zlearn.upsert_rule(
        rules,
        key,
        cat,
        genre=gen,
        source="dashboard_apply",
        last_from=str(p.get("date") or "")[:10] or now_iso()[:10],
    )
    zlearn.save_rules(rules)


def update_remote_payload(
    sb,
    payload: dict[str, Any],
    pending: list[dict[str, Any]],
    results: dict[str, dict[str, Any]],
) -> None:
    now = now_iso()
    out_pending: list[dict[str, Any]] = []
    for p in pending:
        pid = str(p.get("id") or "")
        res = results.get(pid)
        row = dict(p)
        if res:
            row["status"] = "applied" if res.get("ok") else "failed"
            row["applied_at"] = now
            row["message"] = str(res.get("message") or "")
        out_pending.append(row)
    payload["pending_category_applies"] = out_pending[-50:]

    fixes = list(payload.get("recent_fixes") or [])
    for f in fixes:
        if not isinstance(f, dict):
            continue
        fid = str(f.get("id") or "")
        for p in out_pending:
            if str(p.get("id") or "") != fid and str(p.get("row_key") or "") != str(
                f.get("row_key") or ""
            ):
                continue
            if p.get("status") == "applied":
                f["ok"] = True
                f["status"] = "pending_confirm"
                f["message"] = "dashboard_applied"
            elif p.get("status") == "failed":
                f["ok"] = False
                f["status"] = "failed"
                f["message"] = p.get("message")
    payload["recent_fixes"] = fixes[-40:]

    reviews = list(payload.get("category_reviews") or [])
    applied_keys = {
        str(p.get("row_key") or "")
        for p in out_pending
        if p.get("status") == "applied" and p.get("row_key")
    }
    payload["category_reviews"] = [
        r
        for r in reviews
        if isinstance(r, dict)
        and str(r.get("row_key") or "") not in applied_keys
    ]

    sb.table("watch_status").update(
        {"payload": payload, "updated_at": now}
    ).eq("id", WATCH_ID).execute()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Dashboard Zaim category apply")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--limit", type=int, default=10)
    ap.add_argument(
        "--lock-wait",
        type=int,
        default=0,
        help="Playwright 共有ロックの待機秒（0 は即時。CSV週次と競合時は次回再試行）",
    )
    args = ap.parse_args(argv)

    sb = supabase_client()
    row = (
        sb.table("watch_status")
        .select("payload")
        .eq("id", WATCH_ID)
        .maybe_single()
        .execute()
    )
    data = row.data if row else None
    if not data:
        print("# no watch_status", flush=True)
        return 0
    payload = dict(data.get("payload") or {})
    pending = [
        p
        for p in (payload.get("pending_category_applies") or [])
        if isinstance(p, dict) and p.get("status") == "queued"
    ]
    if not pending:
        print("# no queued dashboard applies", flush=True)
        return 0

    batch = pending[: max(1, args.limit)]
    actions = [pending_to_action(p) for p in batch]
    print(f"# dashboard apply queued={len(batch)}", flush=True)

    if args.dry_run:
        for i, a in enumerate(actions, 1):
            print(
                f"  {i}. {a.get('date')} {a.get('shop')} → {a.get('value')}",
                flush=True,
            )
        return 0

    if not acquire_playwright_lock(wait_sec=args.lock_wait):
        print(
            "# playwright lock busy; 費目キューは残置（CSV週次と競合、次回再試行）",
            flush=True,
        )
        return 4
    try:
        entries = zrunner.apply_actions(actions, dry_run=False, limit=len(actions))
    finally:
        release_playwright_lock()
    results: dict[str, dict[str, Any]] = {}
    cl = load_changelog()
    for p, e in zip(batch, entries):
        pid = str(p.get("id") or "")
        results[pid] = {"ok": bool(e.get("ok")), "message": e.get("message")}
        learn_from_apply(p, ok=bool(e.get("ok")))
        e["source"] = "dashboard_apply"
        zrunner.merge_changelog_entries(cl, [e])
    save_changelog(cl)

    ok_row_keys = {
        str(p.get("row_key") or "")
        for p, e in zip(batch, entries)
        if e.get("ok") and p.get("row_key")
    }
    if ok_row_keys:
        zrunner.mark_reviews_auto_applied(ok_row_keys)

    update_remote_payload(sb, payload, batch, results)
    applied_n = sum(1 for r in results.values() if r.get("ok"))
    print(f"# dashboard apply done ok={applied_n}/{len(batch)}", flush=True)
    return 0 if applied_n == len(batch) else 1


if __name__ == "__main__":
    raise SystemExit(main())
