#!/usr/bin/env python3
"""あかつき債券の週次値動きを Zaim（財務）へ、過去と同じ型で登録する。

学習元（Zaim CSV 2026-04-15）:
  payment, α.B.C.投資, 外国債減収, あかつき証券, 50944円, 集計に含めない

増収は同日の bloomo「H.株増収」に合わせ、あかつき口座への income。
集計は減収と同じく含めない（週次評価で家計を汚さない）。

初回成功はベースラインのみ（0からの巨大増収は作らない）。

  cd ~/git-repos && set -a && source .env.jarvis_private && set +a
  ~/selenium_env/venv/bin/python scripts/jarvis_zaim_akatsuki_weekly.py --dry-run
  ~/selenium_env/venv/bin/python scripts/jarvis_zaim_akatsuki_weekly.py --apply --yes
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

STATE_PATH = REPO / ".jarvis_state" / "akatsuki_zaim_weekly.json"
FINANCE = REPO / "215_kamiooya" / "C1_cursor" / "finance"
CREATE = FINANCE / "zaim_budget_sync" / "zaim_money_create.py"
PY = Path.home() / "selenium_env" / "venv" / "bin" / "python"
ENV_FILE = FINANCE / ".env.akatsuki"

ACCOUNT = "あかつき証券"
CAT_DOWN = "α.B.C.投資"
GENRE_DOWN = "外国債減収"
CAT_UP = "J.外国債増収"


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
    if not ENV_FILE.is_file() and not (
        os.environ.get("AKATSUKI_BRANCH_CODE") and os.environ.get("AKATSUKI_LOGIN_PASSWORD")
    ):
        raise SystemExit("AKATSUKI_* が未設定です（.env.akatsuki / jarvis_private）")
    args = [py_exe(), str(FINANCE / "akatsuki_bond_balance.py"), "--headless", "--json"]
    if ENV_FILE.is_file():
        args += ["--env-file", str(ENV_FILE)]
    r = subprocess.run(args, cwd=str(FINANCE), capture_output=True, text=True, timeout=180)
    if r.returncode != 0:
        err = (r.stderr or r.stdout or "fetch fail").strip().splitlines()
        raise RuntimeError(err[-1] if err else "akatsuki fetch failed")
    line = (r.stdout or "").strip().splitlines()[-1]
    data = json.loads(line)
    return int(data["total_jpy"])


def plan_entry(prev: int, curr: int, day: str) -> dict[str, Any] | None:
    delta = curr - prev
    if delta == 0:
        return None
    comment = f"週次評価 {prev:,}→{curr:,}"
    if delta < 0:
        return {
            "kind": "payment",
            "amount": abs(delta),
            "date": day,
            "account": ACCOUNT,
            "category": CAT_DOWN,
            "genre": GENRE_DOWN,
            "comment": comment,
            "exclude": True,
        }
    return {
        "kind": "income",
        "amount": delta,
        "date": day,
        "account": ACCOUNT,
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
    ap = argparse.ArgumentParser(description="あかつき週次 → Zaim")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--yes", action="store_true")
    ap.add_argument("--headless", action="store_true")
    ap.add_argument("--value", type=int, default=0, help="取得済み評価額（週次本体から渡す）")
    ap.add_argument("--skip-fetch", action="store_true")
    args = ap.parse_args()

    if os.environ.get("JARVIS_AKATSUKI_ZAIM_DISABLE") == "1":
        print("# skip: JARVIS_AKATSUKI_ZAIM_DISABLE=1")
        return 0

    st = load_state()
    day = today_jst().isoformat()
    if args.skip_fetch and args.value:
        curr = int(args.value)
    else:
        print("# fetch akatsuki ...")
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
            }
        )
        print(f"📎 あかつき財務: 初回ベースライン {curr:,}円（差分登録なし）")
        return 0

    prev = int(prev)
    if st.get("last_posted_date") == day:
        print(f"# skip: already posted today ({day})")
        return 0

    entry = plan_entry(prev, curr, day)
    if entry is None:
        print("📎 あかつき財務: 動きなし")
        save_state({**st, "last_checked_at": now_iso(), "last_value_jpy": curr})
        return 0

    print(
        f"📎 あかつき財務案: {entry['kind']} {entry['category']}/{entry['genre'] or '-'} "
        f"{ACCOUNT} ¥{entry['amount']:,} 集計除外  # {entry['comment']}"
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
            }
        )
        print(f"# posted and state updated value={curr:,}")
    else:
        print("# dry-run: state の評価額は更新していません")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
