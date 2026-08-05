#!/usr/bin/env python3
"""
Zaim Watch 週次ランナー: 品質検知 → 安全な集計設定の自動適用 → changelog → push。

  cd ~/git-repos && set -a && source .env.jarvis_private && set +a
  python scripts/jarvis_zaim_watch_runner.py
  python scripts/jarvis_zaim_watch_runner.py --dry-run
  python scripts/jarvis_zaim_watch_runner.py --skip-apply
  python scripts/jarvis_zaim_watch_runner.py --skip-push

CSV 週次エクスポート後に呼ぶ想定。セッション切れ時は apply をスキップして warn。
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

JST = ZoneInfo("Asia/Tokyo")
REPO = Path(__file__).resolve().parents[1]
STATE = REPO / ".jarvis_state"
WATCH_PATH = STATE / "zaim_quality_watch.json"
CHANGELOG_PATH = STATE / "zaim_watch_changelog.json"
REVIEW_BATCH_PATH = STATE / "zaim_review_batch.json"
PY = Path.home() / "selenium_env" / "venv" / "bin" / "python"
EXE = str(PY) if PY.is_file() else sys.executable

SAFE_TARGETS = {"card", "smart", "must_include", "amazon_card", "amazon_site"}


def now_iso() -> str:
    return datetime.now(JST).strftime("%Y-%m-%dT%H:%M:%S%z")


def category_review_id(row: dict[str, Any]) -> str:
    return "|".join(
        [
            "cat",
            str(row.get("date") or ""),
            str(row.get("shop") or "")[:40],
            str(int(round(float(row.get("amount") or 0)))),
            str(row.get("category") or "")[:40],
        ]
    )


def load_review_batch() -> dict[str, Any]:
    if REVIEW_BATCH_PATH.is_file():
        try:
            return json.loads(REVIEW_BATCH_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def save_review_batch(data: dict[str, Any]) -> None:
    REVIEW_BATCH_PATH.parent.mkdir(parents=True, exist_ok=True)
    data["updated_at"] = now_iso()
    REVIEW_BATCH_PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def sync_category_reviews_to_changelog(cl: dict[str, Any]) -> tuple[int, list[dict[str, Any]]]:
    """品質検知の費目見直しを changelog に pending で載せる（Web 自動変更なし）。"""
    if not WATCH_PATH.is_file():
        return 0, []
    data = json.loads(WATCH_PATH.read_text(encoding="utf-8"))
    cats = list(data.get("category_reviews") or [])
    existing = {e.get("id") for e in cl.get("entries") or []}
    added: list[dict[str, Any]] = []
    for c in cats:
        eid = category_review_id(c)
        if eid in existing:
            continue
        entry = {
            "id": eid,
            "kind": "category_review",
            "date": c.get("date"),
            "shop": c.get("shop"),
            "amount": c.get("amount"),
            "category": c.get("category"),
            "suggest": c.get("suggest"),
            "proposal": c.get("proposal"),
            "applied_at": now_iso(),
            "ok": True,
            "status": "pending_confirm",
            "message": "reviewed_notice",
        }
        cl.setdefault("entries", []).append(entry)
        added.append(entry)
        existing.add(eid)
    return len(added), added


def open_review_batch(
    *,
    aggregate_applied: int,
    category_added: int,
    category_total: int,
) -> None:
    """ホームお知らせ用バッチ。新規直し／費目見直しがあれば未確認バナーを立てる。"""
    prev = load_review_batch()
    something_new = aggregate_applied > 0 or category_added > 0
    if not something_new:
        if category_total > 0 and not prev.get("batch_id"):
            something_new = True
        else:
            return
    batch_id = now_iso()
    lines = []
    if aggregate_applied:
        lines.append(f"集計設定を {aggregate_applied} 件直しました")
    if category_total:
        lines.append(f"費目（その他等）を {category_total} 件見直しました")
    if not lines:
        lines.append("Zaim を見直しました")
    save_review_batch(
        {
            **{k: v for k, v in prev.items() if k.startswith("history") is False},
            "batch_id": batch_id,
            "reviewed_at": batch_id,
            "aggregate_applied": aggregate_applied,
            "category_added": category_added,
            "category_total": category_total,
            "lines": lines,
            "dashboard_ack_batch_id": None,
            "show_banner": True,
        }
    )
    print(f"# review batch {batch_id} lines={lines}", flush=True)


def fix_id(action: dict[str, Any]) -> str:
    return "|".join(
        [
            str(action.get("date") or ""),
            str(action.get("shop") or "")[:40],
            str(int(round(float(action.get("amount") or 0)))),
            str(action.get("value") or ""),
            str(action.get("target") or ""),
        ]
    )


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


def run_script(script: str, extra: list[str] | None = None, timeout: int = 180) -> int:
    cmd = [EXE, str(REPO / "scripts" / script), *(extra or [])]
    print(f"# run {' '.join(cmd)}", flush=True)
    r = subprocess.run(cmd, cwd=str(REPO), timeout=timeout)
    return r.returncode


def safe_actions_from_watch() -> list[dict[str, Any]]:
    if not WATCH_PATH.is_file():
        return []
    data = json.loads(WATCH_PATH.read_text(encoding="utf-8"))
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for src in (data.get("proposed_actions") or [], data.get("action_items") or []):
        for row in src:
            a = row.get("action") if isinstance(row, dict) and "action" in row else row
            if not isinstance(a, dict):
                continue
            if a.get("action") != "set_aggregate":
                continue
            if a.get("target") not in SAFE_TARGETS:
                continue
            if a.get("value") not in ("include", "exclude"):
                continue
            fid = fix_id(a)
            if fid in seen:
                continue
            seen.add(fid)
            out.append(a)
    # samples with both_include / both_exclude / must_include
    for s in data.get("samples") or []:
        a = s.get("action")
        if not isinstance(a, dict):
            continue
        if a.get("action") != "set_aggregate":
            continue
        if a.get("target") not in SAFE_TARGETS and a.get("target") != "card":
            # card/smart from both_include are safe
            if a.get("target") not in ("card", "smart"):
                continue
        if a.get("value") not in ("include", "exclude"):
            continue
        if a.get("target") == "swap_hint":
            continue
        fid = fix_id(a)
        if fid in seen:
            continue
        seen.add(fid)
        out.append(a)
    return out


def already_applied(cl: dict[str, Any], action: dict[str, Any]) -> bool:
    fid = fix_id(action)
    for e in cl.get("entries") or []:
        if e.get("id") == fid and e.get("ok"):
            return True
    return False


def apply_actions(actions: list[dict[str, Any]], *, dry_run: bool, limit: int) -> list[dict[str, Any]]:
    """Returns changelog entries for this run."""
    if not actions:
        return []
    batch = actions[:limit]
    entries: list[dict[str, Any]] = []
    for a in batch:
        entries.append(
            {
                "id": fix_id(a),
                "date": a.get("date"),
                "shop": a.get("shop"),
                "amount": a.get("amount"),
                "value": a.get("value"),
                "target": a.get("target"),
                "pay": a.get("pay"),
                "proposal": (
                    f"{a.get('shop')} ¥{float(a.get('amount') or 0):,.0f} "
                    f"→ {a.get('value')} ({a.get('target')})"
                ),
                "applied_at": now_iso(),
                "ok": False,
                "status": "pending_confirm",
                "message": "dry-run" if dry_run else "queued",
            }
        )

    if dry_run:
        print(f"# dry-run {len(batch)} actions", flush=True)
        for i, a in enumerate(batch, 1):
            print(
                f"  {i}. {a.get('date')} ¥{float(a.get('amount') or 0):,.0f} "
                f"shop={str(a.get('shop') or '')[:30]} → {a.get('value')}",
                flush=True,
            )
        for e in entries:
            e["dry_run"] = True
        return entries

    storage = (
        REPO
        / "215_kamiooya"
        / "C1_cursor"
        / "finance"
        / "zaim_budget_sync"
        / ".zaim_storage_state.json"
    )
    if not storage.is_file():
        print("# skip apply: no Zaim session", file=sys.stderr)
        return [
            {
                "id": "session_missing",
                "proposal": "Zaim セッションなし — login 後に再実行",
                "applied_at": now_iso(),
                "ok": False,
                "status": "pending_confirm",
                "message": "session_missing",
            }
        ]

    # 一時 watch JSON を書いて money_apply に渡す
    tmp = STATE / "zaim_watch_apply_batch.json"
    tmp.write_text(
        json.dumps({"proposed_actions": batch}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    cmd = [
        EXE,
        str(REPO / "scripts" / "jarvis_zaim_money_apply.py"),
        "--from-watch",
        "--watch",
        str(tmp),
        "--apply",
        "--yes",
        "--headless",
        "--limit",
        str(limit),
        "--login-method",
        "email",
    ]
    print(f"# run {' '.join(cmd)}", flush=True)
    r = subprocess.run(cmd, cwd=str(REPO), timeout=600)
    last = STATE / "zaim_money_apply_last.json"
    by_key: dict[str, dict[str, Any]] = {}
    if last.is_file():
        try:
            data = json.loads(last.read_text(encoding="utf-8"))
            for row in data.get("results") or []:
                by_key[fix_id(row)] = row
        except Exception:
            pass
    for e in entries:
        row = by_key.get(e["id"])
        if row is not None:
            e["ok"] = bool(row.get("ok"))
            e["message"] = str(row.get("message") or "")
            e["status"] = "pending_confirm" if e["ok"] else "failed"
        else:
            e["ok"] = r.returncode == 0
            e["status"] = "pending_confirm" if e["ok"] else "failed"
            e["message"] = f"apply_rc={r.returncode}"
    print(f"# apply rc={r.returncode}", flush=True)
    return entries


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--skip-apply", action="store_true")
    ap.add_argument("--skip-push", action="store_true")
    ap.add_argument("--skip-finance", action="store_true")
    ap.add_argument("--limit", type=int, default=8)
    args = ap.parse_args(argv)

    year = datetime.now(JST).year

    # 1) quality + bank check
    run_script("jarvis_zaim_quality_check.py")
    run_script("jarvis_zaim_bank_sync_check.py")

    # 2) finance metrics this year + last year
    if not args.skip_finance:
        run_script("jarvis_finance_metrics.py", ["--year", str(year), "--push"], timeout=120)
        rc = run_script(
            "jarvis_finance_metrics.py",
            ["--year", str(year - 1), "--push"],
            timeout=120,
        )
        if rc != 0:
            print(f"# prev year finance push rc={rc} (CSV が無ければ無視可)", flush=True)

    # 3) safe apply
    cl = load_changelog()
    new_entries: list[dict[str, Any]] = []
    applied_ok = 0
    if not args.skip_apply:
        actions = [
            a for a in safe_actions_from_watch() if not already_applied(cl, a)
        ]
        print(f"# safe actions pending apply: {len(actions)}", flush=True)
        new_entries = apply_actions(actions, dry_run=args.dry_run, limit=args.limit)
        if new_entries and not args.dry_run:
            existing_ids = {e.get("id") for e in cl.get("entries") or []}
            for e in new_entries:
                if e.get("ok"):
                    applied_ok += 1
                if e.get("id") in existing_ids and e.get("ok"):
                    for old in cl["entries"]:
                        if old.get("id") == e.get("id"):
                            old.update(e)
                            break
                else:
                    cl.setdefault("entries", []).append(e)
            save_changelog(cl)
            run_script("jarvis_zaim_quality_check.py")
        elif new_entries and args.dry_run:
            print(json.dumps(new_entries, ensure_ascii=False, indent=2))

    # 3b) 費目見直しを changelog / ホームお知らせバッチへ
    cat_added = 0
    cat_total = 0
    if not args.dry_run:
        cl = load_changelog()
        cat_added, _ = sync_category_reviews_to_changelog(cl)
        if cat_added:
            save_changelog(cl)
        if WATCH_PATH.is_file():
            try:
                w = json.loads(WATCH_PATH.read_text(encoding="utf-8"))
                cat_total = int(w.get("category_review_count") or 0)
            except Exception:
                cat_total = 0
        open_review_batch(
            aggregate_applied=applied_ok,
            category_added=cat_added,
            category_total=cat_total,
        )

    # 4) push watch (+ merge happens in dashboard_push)
    if not args.skip_push and not args.dry_run:
        run_script("jarvis_dashboard_push.py", ["--watch-only"], timeout=180)

    print(
        f"# Zaim Watch runner done applied={applied_ok} category_added={cat_added}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
