#!/usr/bin/env python3
"""Bloomo（MF経由評価）の週次値動きを Zaim（財務）へ登録する。

学習メモ（あかつき週次コメント）: 増収は「H.株増収」。減収は α.B.C.投資 / 株減収。
口座名は ZAIM_BLOOMO_ACCOUNT（既定 Bloomo）。

  cd ~/git-repos && set -a && source .env.jarvis_private && set +a
  ~/selenium_env/venv/bin/python scripts/jarvis_zaim_bloomo_weekly.py --dry-run
  ~/selenium_env/venv/bin/python scripts/jarvis_zaim_bloomo_weekly.py --apply --yes --headless
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from jarvis_trade_common import JST, REPO, today_jst

STATE_PATH = REPO / ".jarvis_state" / "bloomo_zaim_weekly.json"
FINANCE = REPO / "215_kamiooya" / "C1_cursor" / "finance"
CREATE = FINANCE / "zaim_budget_sync" / "zaim_money_create.py"
PY = Path.home() / "selenium_env" / "venv" / "bin" / "python"
MF_SCRIPT = REPO / "scripts" / "jarvis_mf_bloomo_balance.py"

CAT_DOWN = "α.B.C.投資"
GENRE_DOWN = "株減収"
CAT_UP = "H.株増収"


def account_name() -> str:
    return (os.environ.get("ZAIM_BLOOMO_ACCOUNT") or "Bloomo").strip() or "Bloomo"


def now_iso() -> str:
    return datetime.now(JST).strftime("%Y-%m-%dT%H:%M:%S%z")


def load_state() -> dict[str, Any]:
    if not STATE_PATH.is_file():
        return {}
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_state(data: dict[str, Any]) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def py_exe() -> str:
    return str(PY) if PY.is_file() else sys.executable


def fetch_current() -> int:
    args = [py_exe(), str(MF_SCRIPT), "--headless", "--json"]
    r = subprocess.run(args, cwd=str(REPO), capture_output=True, text=True, timeout=240)
    if r.returncode != 0:
        err = (r.stderr or r.stdout or "fetch fail").strip().splitlines()
        raise RuntimeError(err[-1] if err else "mf bloomo fetch failed")
    line = (r.stdout or "").strip().splitlines()[-1]
    data = json.loads(line)
    if data.get("status") != "ok":
        raise RuntimeError(data.get("reason") or "mf bloomo not ok")
    return int(data["value_jpy"])


def plan_entry(prev: int, curr: int, day: str) -> dict[str, Any] | None:
    delta = curr - prev
    if delta == 0:
        return None
    comment = f"週次評価(MF) {prev:,}→{curr:,}"
    acc = account_name()
    if delta < 0:
        return {
            "kind": "payment",
            "amount": abs(delta),
            "date": day,
            "account": acc,
            "category": CAT_DOWN,
            "genre": GENRE_DOWN,
            "comment": comment,
            "exclude": True,
        }
    return {
        "kind": "income",
        "amount": delta,
        "date": day,
        "account": acc,
        "category": CAT_UP,
        "genre": "",
        "comment": comment,
        "exclude": True,
    }


def post_zaim(entry: dict[str, Any], *, apply: bool, yes: bool, headless: bool) -> int:
    args = [
        py_exe(),
        str(CREATE),
        "--kind",
        entry["kind"],
        "--amount",
        str(entry["amount"]),
        "--date",
        entry["date"],
        "--account",
        entry["account"],
        "--category",
        entry["category"],
        "--genre",
        entry["genre"],
        "--comment",
        entry["comment"],
    ]
    if entry.get("exclude"):
        args.append("--exclude")
    if apply and yes:
        args += ["--apply", "--yes"]
        if headless:
            args.append("--headless")
    else:
        args.append("--dry-run")
    print(f"# zaim {' '.join(args[2:])}")
    return subprocess.run(args, cwd=str(CREATE.parent), check=False).returncode


def main() -> int:
    ap = argparse.ArgumentParser(description="Bloomo 週次 → Zaim")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--yes", action="store_true")
    ap.add_argument("--headless", action="store_true")
    ap.add_argument("--value", type=int, default=0)
    ap.add_argument("--skip-fetch", action="store_true")
    args = ap.parse_args()

    if os.environ.get("JARVIS_BLOOMO_ZAIM_DISABLE") == "1":
        print("# skip: JARVIS_BLOOMO_ZAIM_DISABLE=1")
        return 0

    st = load_state()
    day = today_jst().isoformat()
    if args.skip_fetch and args.value:
        curr = int(args.value)
    else:
        print("# fetch bloomo via MF ...")
        curr = fetch_current()
    print(f"# current={curr:,}")

    prev = st.get("last_value_jpy")
    if prev is None:
        save_state(
            {
                "last_value_jpy": curr,
                "baseline_at": now_iso(),
                "baseline_jpy": curr,
                "last_posted_at": None,
                "note": "初回はベースラインのみ（Zaim未登録）",
                "source": "moneyforward",
            }
        )
        print(f"📎 Bloomo財務: 初回ベースライン {curr:,}円（差分登録なし）")
        return 0

    prev = int(prev)
    if st.get("last_posted_date") == day:
        print(f"# skip: already posted today ({day})")
        return 0

    entry = plan_entry(prev, curr, day)
    if entry is None:
        print("📎 Bloomo財務: 動きなし")
        save_state({**st, "last_checked_at": now_iso(), "last_value_jpy": curr})
        return 0

    print(
        f"📎 Bloomo財務案: {entry['kind']} {entry['category']}/{entry['genre'] or '-'} "
        f"{entry['account']} ¥{entry['amount']:,} 集計除外  # {entry['comment']}"
    )
    do_apply = args.apply and args.yes and not args.dry_run
    rc = post_zaim(entry, apply=do_apply, yes=args.yes, headless=args.headless)
    if rc != 0:
        return rc
    if do_apply:
        save_state(
            {
                **st,
                "last_value_jpy": curr,
                "last_posted_at": now_iso(),
                "last_posted_date": day,
                "last_delta_jpy": curr - prev,
                "last_entry": entry,
                "source": "moneyforward",
            }
        )
        print(f"# posted and state updated value={curr:,}")
    else:
        print("# dry-run: state の評価額は更新していません")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
