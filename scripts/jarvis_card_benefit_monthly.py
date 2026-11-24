#!/usr/bin/env python3
"""614 年間特典ウォッチ — 月次の自動実行本体（launchd／朝オープン取りこぼしから）。

  1. 取得元ごとに取り込む（Olive=Gmail 月次メール／Bonvoy=Zaim）。成功済みの取得元は取り直さない
  2. state へ保存し、読み戻して照合する（取得と保存の成功を月印の前提にする）
  3. 月印 last_monthly_run は「全取得元が成功 かつ 保存の読み戻し成功」の時だけ。Slack の成否には依存しない
  4. Slack #report 短報（状態が変わった時だけ。投稿だけ失敗した時は投稿だけやり直す）
  失敗は --outcome failed で #ops。部分成功・取得待ちは月印を付けず、窓内（28日〜月末）の翌朝に
  未完了の取得元だけを1日1回やり直す。

  python scripts/jarvis_card_benefit_monthly.py [--dry-run] [--force] [--all]

  --force    28日前でも動かす（成功済みの取得元は取り直さない）
  --all      成功済みの取得元も取り直す（手動の全再取得）
  --dry-run  取り込みは行い（取込結果は state に保存する）、Slack は投稿せず表示だけ。
             月印・月の進み具合は記録しない（本番成功に数えない）

停止: JARVIS_CARD_BENEFIT_DISABLE=1（短報だけ止める時は JARVIS_CARD_BENEFIT_SLACK_REPORT_DISABLE=1）
"""
from __future__ import annotations

import argparse
import hashlib
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import jarvis_card_benefit_watch as cbw  # noqa: E402
import jarvis_614_verified_state as vs  # noqa: E402

REPO = cbw.REPO
SLACK = REPO / "scripts" / "jarvis_points_rebate_slack_report.py"
RUN_DAY = 28
_TRUE = ("1", "true", "yes")


def disabled() -> bool:
    return (os.environ.get("JARVIS_CARD_BENEFIT_DISABLE") or "").strip().lower() in _TRUE


def slack_disabled() -> bool:
    return any(
        (os.environ.get(k) or "").strip().lower() in _TRUE
        for k in ("JARVIS_POINTS_REBATE_SLACK_REPORT_DISABLE", "JARVIS_CARD_BENEFIT_SLACK_REPORT_DISABLE")
    )


def _today():
    return datetime.now(cbw.JST).date()


def this_month() -> str:
    return _today().strftime("%Y-%m")


def _month_progress(state: dict[str, Any], month: str) -> dict[str, Any]:
    mon = state.get("monthly")
    if isinstance(mon, dict) and mon.get("month") == month:
        return mon
    return {"month": month, "fetched": {}}


def needs_catchup(now: datetime | None = None) -> bool:
    """朝オープン取りこぼし: 28日以降で、今月まだ完了していない時（1日1回まで）。

    完了 = 月印あり（全取得元が成功し保存を読み戻せた）かつ、短報が出ている（停止中を除く）。"""
    if disabled():
        return False
    now = now or datetime.now(cbw.JST)
    if now.day < RUN_DAY:
        return False
    st = cbw.load_state()
    month = now.strftime("%Y-%m")
    mon = _month_progress(st, month)
    if mon.get("last_attempt_day") == now.strftime("%Y-%m-%d"):
        return False  # 同じ日に何度も取りに行かない
    if st.get("last_monthly_run") != month:
        return True
    return (not slack_disabled()) and not mon.get("slack_fp")


def _slack(*extra: str) -> int:
    return subprocess.run(
        [sys.executable, str(SLACK), "--kind", "card_benefit", *extra], cwd=str(REPO), check=False
    ).returncode


def _ops_failed(error: str, dry: bool) -> None:
    _slack("--outcome", "failed", "--error", error, *(["--dry-run"] if dry else []))


def _fingerprint(month: str, fetched: dict[str, Any], sources: dict[str, Any]) -> str:
    """短報を出し直すかの判定用（金額は含めない）。取得元の状態・基準日が変わった時だけ変わる。"""
    parts = [month]
    for sid in cbw.SOURCE_IDS:
        s = sources.get(sid) or {}
        parts.append(f"{sid}:{fetched.get(sid)}:{s.get('as_of')}:{s.get('error_code')}")
    return hashlib.sha256("|".join(parts).encode()).hexdigest()[:16]


def _save(st: dict[str, Any], label: str, dry: bool) -> bool:
    sv = cbw.save_state_verified(st)
    if sv["ok"]:
        return True
    err = "; ".join(sv["errors"])[:100]
    print(f"❌ state の保存を読み戻して確認できませんでした（{label}）: {err}", file=sys.stderr)
    _ops_failed(f"年間特典の state 保存に失敗（{label}・読み戻し不一致）。取得データは非公開側に一時保持", dry)
    return False


def run(args: argparse.Namespace) -> int:
    today = _today()
    month = today.strftime("%Y-%m")
    dry = bool(args.dry_run)
    try:
        st = cbw.load_state_strict()
    except cbw.StateReadError as e:
        print(f"❌ {e}（上書きせず停止）", file=sys.stderr)
        _ops_failed("年間特典の state を読めないため停止（上書きしていません）", dry)
        return 1
    cfg = cbw.load_config()
    mon = _month_progress(st, month)
    fetched: dict[str, str] = dict(mon.get("fetched") or {})
    if args.all:
        fetched = {}
    targets = [sid for sid in cbw.SOURCE_IDS if fetched.get(sid) != cbw.SRC_OK]

    print(f"# start {datetime.now(cbw.JST).isoformat(timespec='seconds')} 対象={','.join(targets) or 'なし'}")
    results = cbw.refresh_sources(st, cfg, today, only=targets) if targets else {}
    for sid, r in results.items():
        fetched[sid] = r["status"]
        print(f"{sid}: [{r['status_label']}] {r['note']}")  # 金額は note に含まない

    mon = dict(mon, fetched=fetched, run_id=datetime.now(cbw.JST).strftime("%Y%m%dT%H%M%S"))
    if not dry:
        mon["last_attempt_day"] = today.isoformat()
        st["monthly"] = mon

    # 取得と保存（読み戻し照合）。保存を確認できないものを下流（月印・短報）へ渡さない
    if targets or not dry:
        if not _save(st, "取込結果", dry):
            return 1

    failed = [sid for sid in cbw.SOURCE_IDS if fetched.get(sid) == cbw.SRC_FAILED]
    for sid in failed:
        src = (st.get("sources") or {}).get(sid) or {}
        _ops_failed(
            f"年間特典の{'Olive' if sid == 'olive' else 'Bonvoy'}取込に失敗"
            f"（{src.get('error_code') or '不明'}）。次の対応: 連携・Zaim 取込を確認（翌朝に再試行）",
            dry,
        )

    # 月印: 全取得元が成功し、保存を読み戻せた時だけ（Slack・画面の成否とは独立。先に確定して消えない）
    complete = all(fetched.get(sid) == cbw.SRC_OK for sid in cbw.SOURCE_IDS)
    if complete and not dry and st.get("last_monthly_run") != month:
        st["last_monthly_run"] = month
        if not _save(st, "月印", dry):
            return 1
    elif not complete:
        print("# 月印なし（未完了の取得元あり）: " + ", ".join(
            f"{sid}={fetched.get(sid, '未実行')}" for sid in cbw.SOURCE_IDS))

    # Slack 短報: 状態が変わった時だけ。投稿だけ失敗しても取得し直さず、月印も触らない
    fp = _fingerprint(month, fetched, st.get("sources") or {})
    rc = 0
    if all(fetched.get(sid) == cbw.SRC_FAILED for sid in cbw.SOURCE_IDS):
        # 全取得元が失敗なら、前回値だけの短報は出さない（#ops に失敗を出し済み。取れたら次回に出す）
        print("# 短報なし（全取得元が失敗）")
    elif args.all or dry or mon.get("slack_fp") != fp:
        rc = _slack("--from-state", *(["--dry-run"] if dry else []))
        if rc != 0:
            _ops_failed(f"短報の投稿に失敗（exit {rc}）。取得・保存・月印は済み。投稿だけ再試行", dry)
            return rc
        if not dry and not slack_disabled():
            mon["slack_fp"] = fp
            mon["slack_posted_at"] = datetime.now(cbw.JST).isoformat(timespec="seconds")
            st["monthly"] = mon
            if not _save(st, "短報記録", dry):
                return 1
    print("# end " + ("ok" if not failed else "failed=" + ",".join(failed)))
    return 1 if failed else rc


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true", help="取り込みは行い、Slack は投稿せず表示だけ")
    ap.add_argument("--force", action="store_true", help="28日前でも動かす（成功済みは取り直さない）")
    ap.add_argument("--all", action="store_true", help="成功済みの取得元も取り直す")
    args = ap.parse_args(argv)

    if disabled():
        print("⏭ JARVIS_CARD_BENEFIT_DISABLE=1 — 実行スキップ")
        return 0
    if not args.force and not args.all and _today().day < RUN_DAY:
        print("⏭ 28日前のためスキップ（--force で実行）")
        return 0
    try:
        with vs.file_lock(cbw.lock_path()):
            return run(args)
    except vs.LockBusy:
        print("⏭ 別の年間特典の実行中のためスキップ（排他）")
        return 0


if __name__ == "__main__":
    sys.exit(main())
