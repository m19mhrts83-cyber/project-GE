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
import jarvis_614_display as display614  # noqa: E402
import jarvis_614_ops as ops614  # noqa: E402
import jarvis_614_runlog as runlog614  # noqa: E402
import jarvis_614_verified_state as vs  # noqa: E402

REPO = cbw.REPO
SLACK = REPO / "scripts" / "jarvis_points_rebate_slack_report.py"
RUN_DAY = 28
_TRUE = ("1", "true", "yes")


def disabled() -> bool:
    """系統別の停止、または 614 全体停止（全体停止は --force でも解除しない）。"""
    return (
        (os.environ.get("JARVIS_CARD_BENEFIT_DISABLE") or "").strip().lower() in _TRUE
        or ops614.global_stop()
    )


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


SYS = "card_benefit"
_STAGE_LABEL = {"fetch": "n13/n14 取込", "save": "n16 保存", "stamp": "n26 月印", "push": "n17 画面反映(push)",
                "display": "n18 画面反映の確認", "slack": "n19 Slack 短報"}


def _notify(rec: runlog614.RunRecord, stage: str, cause: str, next_action: str, dry: bool) -> None:
    ops614.notify_ops(
        system=SYS, stage=_STAGE_LABEL.get(stage, stage), cause=cause, next_action=next_action,
        run_id=rec.run_id, dry_run=dry,
    )


def _fingerprint(month: str, fetched: dict[str, Any], sources: dict[str, Any]) -> str:
    """短報を出し直すかの判定用（金額は含めない）。取得元の状態・基準日が変わった時だけ変わる。"""
    parts = [month]
    for sid in cbw.SOURCE_IDS:
        s = sources.get(sid) or {}
        parts.append(f"{sid}:{fetched.get(sid)}:{s.get('as_of')}:{s.get('error_code')}")
    return hashlib.sha256("|".join(parts).encode()).hexdigest()[:16]


def _save(st: dict[str, Any], label: str, rec: runlog614.RunRecord, dry: bool) -> bool:
    sv = cbw.save_state_verified(st)
    if sv["ok"]:
        return True
    err = "; ".join(sv["errors"])[:100]
    print(f"❌ state の保存を読み戻して確認できませんでした（{label}）: {err}", file=sys.stderr)
    rec.stage(SYS, "save", "failed", f"{label}: 読み戻し不一致", "save_verify_mismatch")
    rec.stage(SYS, "save_verify", "failed", err, "save_verify_mismatch")
    _notify(rec, "save", f"state の保存を読み戻して確認できず（{label}）。取得データは非公開側に一時保持",
            "state 領域の空き・権限を確認し、手動で --force 実行（外部は取り直さず保存だけやり直し）", dry)
    return False


def _worst(statuses: list[str]) -> str:
    order = {"failed": 4, "partial": 3, "waiting": 2, "unconfirmed": 3, "success": 0}
    return max(statuses, key=lambda x: order.get(x, 3)) if statuses else "skipped"


def _stage_status_from_source(st: str) -> str:
    return {"success": "success", "partial": "partial", "waiting": "waiting", "failed": "failed",
            "unconfirmed": "unverified"}.get(st, "unverified")


def run(args: argparse.Namespace, rec: runlog614.RunRecord) -> int:
    today = _today()
    month = today.strftime("%Y-%m")
    dry = bool(args.dry_run)
    if not dry:
        # 保留中の #ops 通知を再送（全体停止中は何もしない）
        try:
            ops614.flush_pending()
        except Exception as e:  # noqa: BLE001
            ops614.emergency_log(f"flush_pending 例外 {type(e).__name__}")
    try:
        st = cbw.load_state_strict()
    except cbw.StateReadError as e:
        print(f"❌ {e}（上書きせず停止）", file=sys.stderr)
        rec.stage(SYS, "fetch", "failed", "state を読めず停止", "state_unreadable")
        _notify(rec, "save", "年間特典の state を読めないため停止（上書きしていません）",
                "state ファイルの破損を確認（.bak から戻す）", dry)
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
    if targets:
        rec.stage(SYS, "fetch", _stage_status_from_source(_worst([fetched[s] for s in targets])),
                  "・".join(f"{s}={fetched[s]}" for s in targets))
    else:
        rec.stage(SYS, "fetch", "skipped", "全取得元が成功済み（取り直さない）")

    mon = dict(mon, fetched=fetched, run_id=rec.run_id)
    if not dry:
        mon["last_attempt_day"] = today.isoformat()
        st["monthly"] = mon

    # 取得と保存（読み戻し照合）。保存を確認できないものを下流（月印・短報）へ渡さない
    if targets or not dry:
        if not _save(st, "取込結果", rec, dry):
            return 1
        rec.stage(SYS, "save", "success", "tmp→置換で保存")
        rec.stage(SYS, "save_verify", "success", "読み戻し照合 OK")
    else:
        rec.stage(SYS, "save", "skipped", "dry-run で取得なし")

    failed = [sid for sid in cbw.SOURCE_IDS if fetched.get(sid) == cbw.SRC_FAILED]
    for sid in failed:
        src = (st.get("sources") or {}).get(sid) or {}
        _notify(
            rec, "fetch",
            f"{'Olive' if sid == 'olive' else 'Bonvoy'}の取込に失敗（{src.get('error_code') or '不明'}）",
            "連携・Zaim 取込を確認（翌朝に自動で再試行）", dry,
        )

    # 月印: 全取得元が成功し、保存を読み戻せた時だけ（Slack・画面の成否とは独立。先に確定して消えない）
    complete = all(fetched.get(sid) == cbw.SRC_OK for sid in cbw.SOURCE_IDS)
    if complete and not dry and st.get("last_monthly_run") != month:
        st["last_monthly_run"] = month
        if not _save(st, "月印", rec, dry):
            rec.stage(SYS, "stamp", "failed", "月印の保存を確認できず", "save_verify_mismatch")
            return 1
        rec.stage(SYS, "stamp", "success", f"{month} の月印を保存")
    elif complete and not dry:
        rec.stage(SYS, "stamp", "skipped", "今月は月印済み")
    elif not complete:
        print("# 月印なし（未完了の取得元あり）: " + ", ".join(
            f"{sid}={fetched.get(sid, '未実行')}" for sid in cbw.SOURCE_IDS))
        rec.stage(SYS, "stamp", "skipped", "未完了の取得元あり: " + ",".join(
            f"{sid}={fetched.get(sid, '未実行')}" for sid in cbw.SOURCE_IDS))
    else:
        rec.stage(SYS, "stamp", "not_applicable", "dry-run（月印は付けない）")

    # 画面反映（保存済み state から push → 実表示を読み戻して照合。不一致は最大1回再 push）。
    # 失敗しても取得・保存・月印は取り消さない
    if dry:
        rec.stage(SYS, "push", "not_applicable", "dry-run")
        rec.stage(SYS, "display", "not_applicable", "dry-run")
    elif all(fetched.get(sid) == cbw.SRC_FAILED for sid in cbw.SOURCE_IDS):
        rec.stage(SYS, "push", "skipped", "全取得元が失敗（新しい値なし）")
        rec.stage(SYS, "display", "skipped", "全取得元が失敗（新しい値なし）")
    else:
        sync = display614.sync_and_verify(["vpoint"])
        rec.stage(SYS, "push", "success" if sync["push"] == "success" else "failed",
                  f"{sync['attempts']}回目まで", None if sync["push"] == "success" else "push_failed")
        disp = {"success": "success", "failed": "failed"}.get(sync["display"], "unverified")
        rec.stage(SYS, "display", disp, sync["error"] or "画面の行を読み戻して一致",
                  None if disp == "success" else f"display_{sync['display']}")
        if sync["push"] != "success" or sync["display"] == "failed":
            _notify(rec, "display" if sync["push"] == "success" else "push",
                    sync["error"] or "画面反映を確認できず（取得・保存・月印は済み）",
                    "ダッシュボードの /vpoint を確認。保存済み state から再 push（dashboard_push.py --watch-only）", dry)

    # Slack 短報: 状態が変わった時だけ。投稿だけ失敗しても取得し直さず、月印も触らない
    fp = _fingerprint(month, fetched, st.get("sources") or {})
    rc = 0
    if all(fetched.get(sid) == cbw.SRC_FAILED for sid in cbw.SOURCE_IDS):
        # 全取得元が失敗なら、前回値だけの短報は出さない（#ops に失敗を出し済み。取れたら次回に出す）
        print("# 短報なし（全取得元が失敗）")
        rec.stage(SYS, "slack", "skipped", "全取得元が失敗")
    elif args.all or dry or mon.get("slack_fp") != fp:
        rc = _slack("--from-state", *(["--dry-run"] if dry else []))
        if dry:
            rec.stage(SYS, "slack", "not_applicable", "dry-run（未配信の控えだけ）")
        elif rc == 0 and slack_disabled():
            rec.stage(SYS, "slack", "skipped", "短報は停止中")
        elif rc == 0:
            rec.stage(SYS, "slack", "success", "投稿済み（控え保存・結果追記済み）")
        elif rc == 5:
            rec.stage(SYS, "slack", "skipped", "614 全体停止中のため送らず（投稿済みとして数えない）")
        elif rc == 4:
            rec.stage(SYS, "slack", "unverified", "投稿結果不明（再投稿していない）", "post_unknown")
        elif rc == 3:
            rec.stage(SYS, "slack", "failed", "控えを保存できず投稿を保留", "archive_failed")
        else:
            rec.stage(SYS, "slack", "failed", f"exit {rc}", "post_failed")
        if rc == 5:
            print("# end ok（短報は全体停止中のため未投稿）")
            return 1 if failed else 0  # 投稿していないので短報済みの印は付けない
        if rc not in (0, 3, 4):
            _notify(rec, "slack", f"短報の投稿に失敗（exit {rc}）。取得・保存・月印は済み",
                    "投稿だけ翌朝に自動で再試行", dry)
        if rc == 4 and not dry:
            # 結果不明は自動で再投稿しない。同じ状態の短報は出したものとして扱い、人の確認に委ねる
            mon["slack_fp"] = fp
            mon["slack_result"] = "unknown"
            st["monthly"] = mon
            if not _save(st, "短報記録", rec, dry):
                return 1
        if rc != 0:
            return rc if rc != 4 else 1
        if not dry and not slack_disabled():
            mon["slack_fp"] = fp
            mon["slack_result"] = "sent"
            mon["slack_posted_at"] = datetime.now(cbw.JST).isoformat(timespec="seconds")
            st["monthly"] = mon
            if not _save(st, "短報記録", rec, dry):
                return 1
    else:
        rec.stage(SYS, "slack", "skipped", "状態が変わっていないため再投稿しない")
    print("# end " + ("ok" if not failed else "failed=" + ",".join(failed)))
    return 1 if failed else rc


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true", help="取り込みは行い、Slack は投稿せず表示だけ")
    ap.add_argument("--force", action="store_true", help="28日前でも動かす（成功済みは取り直さない）")
    ap.add_argument("--all", action="store_true", help="成功済みの取得元も取り直す")
    args = ap.parse_args(argv)

    rec = runlog614.RunRecord(
        run_id=runlog614.new_run_id(SYS), dry_run=args.dry_run,
        trigger="manual" if args.all else "auto", script="jarvis_card_benefit_monthly.py",
    )
    os.environ["JARVIS_614_RUN_ID"] = rec.run_id  # 子（Slack 短報）が同じ run_id を使う
    if disabled():
        print("⏭ JARVIS_CARD_BENEFIT_DISABLE=1／614 全体停止 — 実行スキップ")
        rec.stage(SYS, "fetch", "skipped", "停止中（系統別または全体停止）")
        rec.finish()
        return 0
    if not args.force and not args.all and _today().day < RUN_DAY:
        print("⏭ 28日前のためスキップ（--force で実行）")
        rec.stage(SYS, "fetch", "skipped", "28日前")
        rec.finish()
        return 0
    rc = 1
    try:
        with vs.file_lock(cbw.lock_path()):
            rc = run(args, rec)
    except vs.LockBusy:
        print("⏭ 別の年間特典の実行中のためスキップ（排他）")
        rec.stage(SYS, "fetch", "skipped", "別の実行中（排他）")
        rec.finish()
        return 0
    except Exception as e:  # noqa: BLE001 — 想定外でも無言で落とさない
        # どの工程で落ちたか分からないので、実績のある工程（取得・保存など）を書き換えず『run』に残す
        rec.stage(SYS, "run", "failed", f"想定外のエラー（{type(e).__name__}）", "unexpected_error")
        try:
            _notify(rec, "fetch", f"年間特典の月次が想定外のエラーで止まった（{type(e).__name__}）",
                    "ログ（~/Library/Logs/jarvis_card_benefit/）を確認", bool(args.dry_run))
        finally:
            rec.finish()
        raise
    rec.finish()
    return rc


if __name__ == "__main__":
    sys.exit(main())
