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
PY = Path.home() / "selenium_env" / "venv" / "bin" / "python"
EXE = str(PY) if PY.is_file() else sys.executable

SAFE_TARGETS = {"card", "smart", "must_include", "amazon_card", "amazon_site"}


def now_iso() -> str:
    return datetime.now(JST).strftime("%Y-%m-%dT%H:%M:%S%z")


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
    if not args.skip_apply:
        actions = [
            a for a in safe_actions_from_watch() if not already_applied(cl, a)
        ]
        print(f"# safe actions pending apply: {len(actions)}", flush=True)
        new_entries = apply_actions(actions, dry_run=args.dry_run, limit=args.limit)
        if new_entries and not args.dry_run:
            existing_ids = {e.get("id") for e in cl.get("entries") or []}
            for e in new_entries:
                if e.get("id") in existing_ids and e.get("ok"):
                    for old in cl["entries"]:
                        if old.get("id") == e.get("id"):
                            old.update(e)
                            break
                else:
                    cl.setdefault("entries", []).append(e)
            save_changelog(cl)
            # 適用後に再検知（CSVは古い可能性あり。Web反映後の提案残りを減らす）
            run_script("jarvis_zaim_quality_check.py")
        elif new_entries and args.dry_run:
            print(json.dumps(new_entries, ensure_ascii=False, indent=2))

    # 4) push watch (+ merge happens in dashboard_push)
    if not args.skip_push and not args.dry_run:
        run_script("jarvis_dashboard_push.py", ["--watch-only"], timeout=180)

    print(
        f"# Zaim Watch runner done applied={len([e for e in new_entries if e.get('ok')])}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
