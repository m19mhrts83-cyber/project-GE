#!/usr/bin/env python3
"""Bloomo（MF経由評価）の週次値動きを Zaim（財務）へ登録する。

学習メモ: 増収は「H.株増収」。減収は α.B.C.投資 / 外国株減収（株減収は未作成のため使わない）。
口座名は ZAIM_BLOOMO_ACCOUNT（既定 bloomo証券。Zaim 上の表記どおり）。
旧名「Bloomo」は不一致で失敗するため、候補を自動リトライして成功名を state に覚える。

  cd ~/git-repos && set -a && source .env.jarvis_private && set +a
  ~/selenium_env/venv/bin/python scripts/jarvis_zaim_bloomo_weekly.py --dry-run
  ~/selenium_env/venv/bin/python scripts/jarvis_zaim_bloomo_weekly.py --apply --yes --headless
  ~/selenium_env/venv/bin/python scripts/jarvis_zaim_bloomo_weekly.py --heal-meta-only
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
# Zaim 実在内訳。旧想定「株減収」は未作成のため外国株減収を先に試す
GENRES_DOWN = ("外国株減収", "株減収", "外国債減収", "")
GENRE_DOWN = GENRES_DOWN[0]
CAT_UP = "H.株増収"

# Zaim 表記ゆれ。先頭ほど優先（env / state のあとに続く）
ACCOUNT_ALIASES = ("bloomo証券", "Bloomo", "bloomo")


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
    STATE_PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def py_exe() -> str:
    return str(PY) if PY.is_file() else sys.executable


def account_candidates(st: dict[str, Any]) -> list[str]:
    preferred = str(st.get("preferred_zaim_account") or "").strip()
    env = (os.environ.get("ZAIM_BLOOMO_ACCOUNT") or "").strip()
    out: list[str] = []
    for a in (preferred, env, *ACCOUNT_ALIASES):
        if a and a not in out:
            out.append(a)
    return out or ["bloomo証券"]


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


def plan_entry(
    prev: int, curr: int, day: str, account: str, *, genre_down: str = GENRE_DOWN
) -> dict[str, Any] | None:
    delta = curr - prev
    if delta == 0:
        return None
    comment = f"週次評価(MF) {prev:,}→{curr:,}"
    if delta < 0:
        return {
            "kind": "payment",
            "amount": abs(delta),
            "date": day,
            "account": account,
            "category": CAT_DOWN,
            "genre": genre_down,
            "comment": comment,
            "exclude": True,
        }
    return {
        "kind": "income",
        "amount": delta,
        "date": day,
        "account": account,
        "category": CAT_UP,
        "genre": "",
        "comment": comment,
        "exclude": True,
    }


def post_zaim(entry: dict[str, Any], *, apply: bool, yes: bool, headless: bool) -> tuple[int, str]:
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
    r = subprocess.run(
        args, cwd=str(CREATE.parent), check=False, capture_output=True, text=True
    )
    if r.stdout:
        print(r.stdout.rstrip())
    if r.stderr:
        print(r.stderr.rstrip(), file=sys.stderr)
    err = ((r.stderr or "") + "\n" + (r.stdout or "")).strip()
    return r.returncode, err


def is_account_missing(err: str) -> bool:
    return "口座が見つかりません" in (err or "")


def is_category_or_genre_missing(err: str) -> bool:
    e = err or ""
    return "カテゴリが見つかりません" in e or "内訳が見つかりません" in e


def mark_sync_meta_bloomo_zaim_ok(*, reason: str) -> None:
    """ホーム鮮度の bloomo_zaim 失敗を、財務反映成功後に自己修復する。"""
    url = os.environ.get("JARVIS_SUPABASE_URL") or os.environ.get("NEXT_PUBLIC_SUPABASE_URL")
    key = os.environ.get("JARVIS_SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        print("# heal-meta skip: no supabase env")
        return
    from supabase import create_client

    sb = create_client(url, key)
    row = (
        sb.table("sync_meta")
        .select("value")
        .eq("key", "portfolio_weekly_summary")
        .maybe_single()
        .execute()
        .data
    )
    if not row or not row.get("value"):
        print("# heal-meta skip: no portfolio_weekly_summary")
        return
    try:
        meta = json.loads(row["value"])
    except json.JSONDecodeError:
        print("# heal-meta skip: bad json")
        return
    sources = meta.get("sources") if isinstance(meta.get("sources"), dict) else {}
    prev = sources.get("bloomo_zaim") if isinstance(sources.get("bloomo_zaim"), dict) else {}
    if prev.get("status") == "ok" and not reason:
        print("# heal-meta: already ok")
        return
    sources["bloomo_zaim"] = {"status": "ok", "reason": reason[:120]}
    meta["sources"] = sources
    # error 件数をざっくり再計算
    err_n = sum(
        1
        for v in sources.values()
        if isinstance(v, dict) and (v.get("status") or "") == "error"
    )
    meta["error"] = err_n
    if err_n == 0:
        meta["last_full_ok"] = True
    ts = now_iso()
    sb.table("sync_meta").upsert(
        {
            "key": "portfolio_weekly_summary",
            "value": json.dumps(meta, ensure_ascii=False),
            "updated_at": ts,
        },
        on_conflict="key",
    ).execute()
    print(f"# heal-meta: bloomo_zaim → ok ({reason[:80]})")


def post_with_account_retry(
    *,
    prev: int,
    curr: int,
    day: str,
    st: dict[str, Any],
    apply: bool,
    yes: bool,
    headless: bool,
) -> tuple[int, dict[str, Any] | None, str | None]:
    """口座名・減収内訳の候補を順に試す。成功した名前を返す。"""
    last_err = ""
    delta = curr - prev
    genre_list: tuple[str, ...] = GENRES_DOWN if delta < 0 else ("",)
    for acc in account_candidates(st):
        for genre in genre_list:
            entry = plan_entry(prev, curr, day, acc, genre_down=genre)
            if entry is None:
                return 0, None, None
            print(
                f"📎 Bloomo財務案: {entry['kind']} {entry['category']}/{entry['genre'] or '-'} "
                f"{entry['account']} ¥{entry['amount']:,} 集計除外  # {entry['comment']}"
            )
            rc, err = post_zaim(entry, apply=apply, yes=yes, headless=headless)
            if rc == 0:
                return 0, entry, acc
            last_err = err or f"exit={rc}"
            if is_account_missing(err):
                print(f"# account miss → retry next alias (failed={acc!r})")
                break  # next account
            if is_category_or_genre_missing(err) and delta < 0:
                print(f"# category/genre miss → retry next genre (failed={genre!r})")
                continue
            # その他の失敗はリトライしない
            return 1, None, last_err
    return 1, None, last_err


def main() -> int:
    ap = argparse.ArgumentParser(description="Bloomo 週次 → Zaim")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--yes", action="store_true")
    ap.add_argument("--headless", action="store_true")
    ap.add_argument("--value", type=int, default=0)
    ap.add_argument("--skip-fetch", action="store_true")
    ap.add_argument(
        "--heal-meta-only",
        action="store_true",
        help="Zaim登録はせず、今日の成功実績があればホーム鮮度の bloomo_zaim を ok に直す",
    )
    args = ap.parse_args()

    if os.environ.get("JARVIS_BLOOMO_ZAIM_DISABLE") == "1":
        print("# skip: JARVIS_BLOOMO_ZAIM_DISABLE=1")
        return 0

    st = load_state()
    day = today_jst().isoformat()

    if args.heal_meta_only:
        acc = (
            st.get("preferred_zaim_account")
            or (st.get("last_entry") or {}).get("account")
            or ""
        )
        posted = st.get("last_posted_date") or st.get("last_posted_at")
        if posted and acc:
            mark_sync_meta_bloomo_zaim_ok(
                reason=f"healed: last post {posted} via {acc}"
            )
            return 0
        print("# heal-meta-only: no successful post to trust")
        return 1

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
                "preferred_zaim_account": account_candidates(st)[0],
            }
        )
        print(f"📎 Bloomo財務: 初回ベースライン {curr:,}円（差分登録なし）")
        return 0

    prev = int(prev)
    if st.get("last_posted_date") == day:
        print(f"# skip: already posted today ({day})")
        # 週次本体が先に失敗メタを書いたあとに手動成功した場合の自己修復
        mark_sync_meta_bloomo_zaim_ok(
            reason=(
                f"already posted {day} "
                f"via {(st.get('last_entry') or {}).get('account') or st.get('preferred_zaim_account')}"
            )
        )
        return 0

    do_apply = args.apply and args.yes and not args.dry_run
    rc, entry, detail = post_with_account_retry(
        prev=prev,
        curr=curr,
        day=day,
        st=st,
        apply=do_apply,
        yes=args.yes,
        headless=args.headless,
    )
    if entry is None and rc == 0:
        print("📎 Bloomo財務: 動きなし")
        save_state({**st, "last_checked_at": now_iso(), "last_value_jpy": curr})
        return 0
    if rc != 0 or entry is None:
        print(f"# fail: {detail}")
        return rc if rc else 1

    winning_account = str(entry.get("account") or detail or "")
    if do_apply:
        save_state(
            {
                **st,
                "last_value_jpy": curr,
                "last_posted_at": now_iso(),
                "last_posted_date": day,
                "last_delta_jpy": curr - prev,
                "last_entry": entry,
                "preferred_zaim_account": winning_account,
                "source": "moneyforward",
            }
        )
        mark_sync_meta_bloomo_zaim_ok(reason=f"posted via {winning_account}")
        print(f"# posted and state updated value={curr:,} account={winning_account}")
    else:
        print(f"# dry-run ok with account={winning_account}（state 未更新）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
