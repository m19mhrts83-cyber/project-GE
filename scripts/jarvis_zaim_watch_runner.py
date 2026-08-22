#!/usr/bin/env python3
"""
Zaim Watch 週次ランナー: 学習 → 品質検知 → 安全な集計／高確信度費目の自動適用 → snapshot → changelog → push。

  cd ~/git-repos && set -a && source .env.jarvis_private && set +a
  python scripts/jarvis_zaim_watch_runner.py
  python scripts/jarvis_zaim_watch_runner.py --dry-run
  python scripts/jarvis_zaim_watch_runner.py --skip-apply
  python scripts/jarvis_zaim_watch_runner.py --skip-push
  python scripts/jarvis_zaim_watch_runner.py --skip-learn

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

sys.path.insert(0, str(Path(__file__).resolve().parent))
import jarvis_zaim_learn as zlearn  # noqa: E402

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
    """低確信度の費目見直しを changelog に pending で載せる（Web 未変更）。high は apply 側。"""
    if not WATCH_PATH.is_file():
        return 0, []
    data = json.loads(WATCH_PATH.read_text(encoding="utf-8"))
    cats = list(data.get("category_reviews") or [])
    existing = {e.get("id") for e in cl.get("entries") or []}
    added: list[dict[str, Any]] = []
    for c in cats:
        if c.get("auto_applied"):
            continue
        if c.get("confidence") == "high" and c.get("suggest"):
            continue
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
            "learn_key": c.get("learn_key"),
            "confidence": c.get("confidence") or "low",
            "proposal": c.get("proposal"),
            "applied_at": now_iso(),
            "ok": True,
            "status": "pending_confirm",
            "message": "reviewed_notice",
            "batch_id": None,
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
    category_applied: int = 0,
    learned_n: int = 0,
) -> None:
    """ホームお知らせ用バッチ。新規直し／費目見直しがあれば未確認バナーを立てる。"""
    prev = load_review_batch()
    something_new = (
        aggregate_applied > 0
        or category_added > 0
        or category_applied > 0
        or learned_n > 0
    )
    if not something_new:
        if category_total > 0 and not prev.get("batch_id"):
            something_new = True
        else:
            return
    batch_id = now_iso()
    lines = []
    if aggregate_applied:
        lines.append(f"集計設定を {aggregate_applied} 件直しました")
    if category_applied:
        lines.append(f"費目を {category_applied} 件自動で直しました")
    if category_total:
        lines.append(f"費目（その他等）を {category_total} 件見直しました")
    if learned_n:
        lines.append(f"手動修正から {learned_n} 件学習しました")
    if not lines:
        lines.append("Zaim を見直しました")
    save_review_batch(
        {
            **{k: v for k, v in prev.items() if k.startswith("history") is False},
            "batch_id": batch_id,
            "reviewed_at": batch_id,
            "aggregate_applied": aggregate_applied,
            "category_added": category_added,
            "category_applied": category_applied,
            "category_total": category_total,
            "learned_n": learned_n,
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


def stamp_changelog_batch_id(cl: dict[str, Any], batch_id: str) -> int:
    """未 stamp の pending/disputed に今回の review batch を付ける。"""
    if not batch_id:
        return 0
    n = 0
    for e in cl.get("entries") or []:
        st = e.get("status") or "pending_confirm"
        if st not in ("pending_confirm", "disputed"):
            continue
        if e.get("batch_id"):
            continue
        e["batch_id"] = batch_id
        n += 1
    return n


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


def category_actions_from_watch() -> list[dict[str, Any]]:
    if not WATCH_PATH.is_file():
        return []
    data = json.loads(WATCH_PATH.read_text(encoding="utf-8"))
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for c in data.get("category_reviews") or []:
        if c.get("confidence") != "high":
            continue
        suggest = str(c.get("suggest") or "").strip()
        if not suggest:
            continue
        a = c.get("action") if isinstance(c.get("action"), dict) else {}
        action = {
            "action": "set_category",
            "target": "category",
            "value": suggest,
            "genre": c.get("suggest_genre") or a.get("genre") or "",
            "date": c.get("date"),
            "shop": c.get("shop"),
            "item": c.get("item"),
            "amount": c.get("amount"),
            "pay": c.get("pay"),
            "method": c.get("method") or "payment",
            "category": c.get("category"),
            "suggest": suggest,
            "learn_key": c.get("learn_key"),
            "row_key": c.get("row_key"),
            "confidence": "high",
        }
        fid = fix_id(action)
        if fid in seen:
            continue
        seen.add(fid)
        out.append(action)
    return out


def already_applied(cl: dict[str, Any], action: dict[str, Any]) -> bool:
    fid = fix_id(action)
    for e in cl.get("entries") or []:
        if e.get("id") != fid:
            continue
        if e.get("status") == "disputed":
            return True
        if e.get("ok"):
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
                "kind": a.get("action") or "set_aggregate",
                "learn_key": a.get("learn_key")
                or zlearn.learn_key(str(a.get("shop") or ""), str(a.get("item") or "")),
                "row_key": a.get("row_key"),
                "item": a.get("item"),
                "batch_id": None,
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


def merge_changelog_entries(cl: dict[str, Any], new_entries: list[dict[str, Any]]) -> int:
    applied_ok = 0
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
    return applied_ok


def mark_reviews_auto_applied(ok_row_keys: set[str]) -> None:
    if not ok_row_keys or not WATCH_PATH.is_file():
        return
    try:
        data = json.loads(WATCH_PATH.read_text(encoding="utf-8"))
    except Exception:
        return
    changed = False
    for c in data.get("category_reviews") or []:
        rk = str(c.get("row_key") or "")
        if rk and rk in ok_row_keys:
            c["auto_applied"] = True
            changed = True
    if changed:
        WATCH_PATH.write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )


def write_learn_snapshot(applied_ok_keys: set[str], batch_id: str) -> int:
    if not WATCH_PATH.is_file():
        return 0
    try:
        data = json.loads(WATCH_PATH.read_text(encoding="utf-8"))
    except Exception:
        return 0
    reviews = list(data.get("category_reviews") or [])
    snap = zlearn.snapshot_from_reviews(
        reviews,
        applied_ok=applied_ok_keys,
        batch_id=batch_id,
        csv_path=str(data.get("csv") or ""),
    )
    zlearn.save_snapshot(snap)
    return len(snap.get("rows") or [])


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--skip-apply", action="store_true")
    ap.add_argument("--skip-push", action="store_true")
    ap.add_argument("--skip-finance", action="store_true")
    ap.add_argument("--skip-learn", action="store_true")
    ap.add_argument("--limit", type=int, default=8)
    args = ap.parse_args(argv)

    year = datetime.now(JST).year
    learned_n = 0

    # 0a) ダッシュボードからキューされた費目変更（Supabase → Zaim Web）
    if not args.skip_apply and not args.dry_run:
        run_script("jarvis_zaim_dashboard_apply.py", timeout=600)

    # 0) 前回 snapshot × 今回 CSV の差分学習
    if not args.skip_learn:
        extra = ["--json"]
        if args.dry_run:
            extra.append("--dry-run")
        run_script("jarvis_zaim_learn.py", extra)
        last = STATE / "zaim_learn_last.json"
        if last.is_file() and not args.dry_run:
            try:
                learned_n = int(json.loads(last.read_text(encoding="utf-8")).get("learned_n") or 0)
            except Exception:
                learned_n = 0

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

    # 3) safe aggregate apply
    cl = load_changelog()
    applied_ok = 0
    cat_applied = 0
    applied_row_keys: set[str] = set()
    if not args.skip_apply:
        actions = [
            a for a in safe_actions_from_watch() if not already_applied(cl, a)
        ]
        print(f"# safe actions pending apply: {len(actions)}", flush=True)
        new_entries = apply_actions(actions, dry_run=args.dry_run, limit=args.limit)
        if new_entries and not args.dry_run:
            applied_ok = merge_changelog_entries(cl, new_entries)
            save_changelog(cl)
            run_script("jarvis_zaim_quality_check.py")
        elif new_entries and args.dry_run:
            print(json.dumps(new_entries, ensure_ascii=False, indent=2))

        # 3b) high-confidence category apply
        cl = load_changelog()
        cat_actions = [
            a for a in category_actions_from_watch() if not already_applied(cl, a)
        ]
        print(f"# category high actions pending apply: {len(cat_actions)}", flush=True)
        if args.dry_run:
            for i, a in enumerate(cat_actions[: args.limit], 1):
                print(
                    f"  {i}. [set_category] {a.get('date')} ¥{float(a.get('amount') or 0):,.0f} "
                    f"{a.get('shop')} → {a.get('value')}",
                    flush=True,
                )
        elif cat_actions:
            cat_entries = apply_actions(cat_actions, dry_run=False, limit=args.limit)
            cat_applied = merge_changelog_entries(cl, cat_entries)
            save_changelog(cl)
            for e, a in zip(cat_entries, cat_actions[: args.limit]):
                if e.get("ok") and a.get("row_key"):
                    applied_row_keys.add(str(a["row_key"]))
            mark_reviews_auto_applied(applied_row_keys)

    # 4) snapshot（自動後の状態をフィックス）
    if not args.dry_run:
        n_snap = write_learn_snapshot(applied_row_keys, now_iso())
        print(f"# learn snapshot rows={n_snap} auto_applied={len(applied_row_keys)}", flush=True)

    # 5) 費目見直し（low）を changelog / ホームお知らせバッチへ
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
                reviews = list(w.get("category_reviews") or [])
                cat_total = sum(1 for c in reviews if not c.get("auto_applied"))
            except Exception:
                cat_total = 0
        open_review_batch(
            aggregate_applied=applied_ok,
            category_added=cat_added,
            category_total=cat_total,
            category_applied=cat_applied,
            learned_n=learned_n,
        )
        rb = load_review_batch()
        bid = str(rb.get("batch_id") or "")
        ack = str(rb.get("dashboard_ack_batch_id") or "")
        if bid and ack != bid:
            cl = load_changelog()
            if stamp_changelog_batch_id(cl, bid):
                save_changelog(cl)

    # 6) push watch
    if not args.skip_push and not args.dry_run:
        run_script("jarvis_dashboard_push.py", ["--watch-only"], timeout=180)

    print(
        f"# Zaim Watch runner done applied={applied_ok} "
        f"category_applied={cat_applied} category_added={cat_added} learned={learned_n}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
