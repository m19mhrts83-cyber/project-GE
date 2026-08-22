#!/usr/bin/env python3
"""
Mac 必須の最新化バンドル（朝オープン裏実行・1日1回）。

夜間フルクラウド化はしない。クラウドできるものは GHA 任せ、
OneDrive path／ローカル依存は Mac 起床後にまとめて追従する。
gmail 取込後に partner レーンの未返信キャッチアップ（night_triage --lane partner）も行う。

  python scripts/jarvis_morning_mac_refresh.py
  python scripts/jarvis_morning_mac_refresh.py --dry-run
  python scripts/jarvis_morning_mac_refresh.py --force
  python scripts/jarvis_morning_mac_refresh.py --with-line   # CHRLINE／オプチャ（重い・任意）

環境変数:
  JARVIS_MORNING_WITH_LINE=1 … --with-line 相当（launchd からオプトイン）
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

JST = ZoneInfo("Asia/Tokyo")
REPO = Path(__file__).resolve().parents[1]
STATE = REPO / ".jarvis_state" / "night_triage"
LAST_REFRESH_PATH = STATE / "last_mac_morning_refresh_date"
LOG_DIR = Path.home() / "Library" / "Logs" / "jarvis_night_triage"
PY = Path.home() / "selenium_env" / "venv" / "bin" / "python"
MANUAL_DIR = (
    REPO
    / "215_kamiooya"
    / "C1_cursor"
    / "1b_Cursorマニュアル"
)
GMAIL_SCRIPT = MANUAL_DIR / "gmail_to_yoritoori.py"
CATCHUP = REPO / "scripts" / "jarvis_triage_yoritoori_catchup.py"
GMAIL_READ_CATCHUP = REPO / "scripts" / "jarvis_triage_gmail_read_catchup.py"
INTENT_SYNC = REPO / "scripts" / "jarvis_intent_from_journal_chat.py"
PUSH = REPO / "scripts" / "jarvis_dashboard_push.py"
KURASHIFT_GROK_MATCH = REPO / "scripts" / "jarvis_kurashift_property_mail_match.py"
POC = REPO / "line_unofficial_poc"
RUN_PATCH = POC / "run_patch.sh"
ZAIM_WEEKLY_STATE = REPO / ".jarvis_state" / "zaim_csv_weekly.json"
ZAIM_WEEKLY_RUNNER = REPO / "launchd" / "zaim_csv_weekly_runner.sh"
ZAIM_LOG_DIR = Path.home() / "Library" / "Logs" / "jarvis_zaim"
WESTUDY_GDRIVE_STATE = REPO / ".jarvis_state" / "westudy_gdrive_weekly.json"
WESTUDY_GDRIVE_RUNNER = REPO / "launchd" / "westudy_gdrive_archive_runner.sh"
WESTUDY_GDRIVE_LOG_DIR = Path.home() / "Library" / "Logs" / "jarvis_westudy_gdrive"
PORTFOLIO_WEEKLY_STATE = REPO / ".jarvis_state" / "portfolio_weekly.json"
PORTFOLIO_WEEKLY_RUNNER = REPO / "launchd" / "portfolio_weekly_runner.sh"
PORTFOLIO_LOG_DIR = Path.home() / "Library" / "Logs" / "jarvis_portfolio"


def now_iso() -> str:
    return datetime.now(JST).strftime("%Y-%m-%dT%H:%M:%S%z")


def today_jst() -> str:
    return datetime.now(JST).strftime("%Y-%m-%d")


def py_exe() -> str:
    return str(PY) if PY.is_file() else sys.executable


def already_refreshed_today() -> bool:
    if not LAST_REFRESH_PATH.is_file():
        return False
    try:
        return LAST_REFRESH_PATH.read_text(encoding="utf-8").strip() == today_jst()
    except OSError:
        return False


def mark_refreshed_today() -> None:
    STATE.mkdir(parents=True, exist_ok=True)
    LAST_REFRESH_PATH.write_text(today_jst() + "\n", encoding="utf-8")


def run_step(
    name: str,
    cmd: list[str],
    *,
    cwd: Path | None = None,
    timeout: int = 600,
    dry_run: bool = False,
    env: dict[str, str] | None = None,
) -> int:
    print(f"# step:{name}: {' '.join(cmd)}", flush=True)
    if dry_run:
        print(f"# dry-run: skip {name}", flush=True)
        return 0
    try:
        r = subprocess.run(
            cmd,
            cwd=str(cwd or REPO),
            env=env,
            timeout=timeout,
            check=False,
        )
        print(f"# step:{name}: exit={r.returncode}", flush=True)
        return int(r.returncode)
    except subprocess.TimeoutExpired:
        print(f"# step:{name}: TIMEOUT ({timeout}s)", file=sys.stderr, flush=True)
        return 124
    except Exception as e:
        print(f"# step:{name}: error {e}", file=sys.stderr, flush=True)
        return 1


def mac_line_running() -> bool:
    """Mac版LINE が起動中なら True（CHRLINE と競合）。"""
    try:
        r = subprocess.run(
            [
                "pgrep",
                "-f",
                r"application\.jp\.naver\.line\.mac|/Applications/LINE\.app",
            ],
            capture_output=True,
            check=False,
        )
        return r.returncode == 0
    except Exception:
        return False


def zaim_csv_needs_catchup(*, max_age_days: int = 6) -> bool:
    """火・金 12:00 の CSV を取りこぼした／失敗したとき True。"""
    if not ZAIM_WEEKLY_STATE.is_file():
        return True
    try:
        data = json.loads(ZAIM_WEEKLY_STATE.read_text(encoding="utf-8"))
    except Exception:
        return True
    if data.get("last_ok") is False:
        return True
    raw = str(data.get("last_success_at") or "").strip()
    if not raw:
        return True
    try:
        # 2026-08-01T23:48:04+0900
        ts = datetime.strptime(raw[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=JST)
    except ValueError:
        return True
    age = datetime.now(JST) - ts
    return age.total_seconds() >= max_age_days * 86400


def _parse_state_ts(raw: str) -> datetime | None:
    raw = (raw or "").strip()
    if not raw:
        return None
    try:
        return datetime.strptime(raw[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=JST)
    except ValueError:
        return None


def this_week_sunday_slot() -> datetime:
    """今週日曜 08:00 JST（本線の予定時刻）。"""
    now = datetime.now(JST)
    days_since_sun = (now.weekday() + 1) % 7
    return now.replace(hour=8, minute=0, second=0, microsecond=0) - timedelta(
        days=days_since_sun
    )


def westudy_gdrive_needs_catchup() -> bool:
    """日曜 08:00 を取りこぼした／失敗したとき True。月曜以降の朝オープンで拾う。"""
    if os.environ.get("JARVIS_WESTUDY_GDRIVE_WEEKLY_DISABLE") == "1":
        return False
    try:
        r = subprocess.run(
            ["pgrep", "-f", "westudy_forum_all.py"],
            capture_output=True,
            check=False,
        )
        if r.returncode == 0:
            return False
    except Exception:
        pass
    now = datetime.now(JST)
    slot = this_week_sunday_slot()
    if now < slot:
        return False
    if not WESTUDY_GDRIVE_STATE.is_file():
        return True
    try:
        data = json.loads(WESTUDY_GDRIVE_STATE.read_text(encoding="utf-8"))
    except Exception:
        return True
    if data.get("last_ok") is False:
        return True
    ts = _parse_state_ts(str(data.get("last_success_at") or ""))
    if ts is None:
        return True
    return ts < slot


def spawn_westudy_gdrive_weekly(*, dry_run: bool) -> str:
    """Drive 添付週次をバックグラウンド起動（朝バンドルをブロックしない）。"""
    if not WESTUDY_GDRIVE_RUNNER.is_file():
        print(f"# westudy_gdrive: missing {WESTUDY_GDRIVE_RUNNER}", file=sys.stderr)
        return "missing"
    if dry_run:
        print("# dry-run: would spawn westudy_gdrive_archive_runner.sh", flush=True)
        return "dry_run"
    WESTUDY_GDRIVE_LOG_DIR.mkdir(parents=True, exist_ok=True)
    out = open(WESTUDY_GDRIVE_LOG_DIR / "morning_catchup.out.log", "a", encoding="utf-8")
    err = open(WESTUDY_GDRIVE_LOG_DIR / "morning_catchup.err.log", "a", encoding="utf-8")
    try:
        out.write(f"\n# spawn {now_iso()}\n")
        out.flush()
        subprocess.Popen(
            ["/bin/zsh", str(WESTUDY_GDRIVE_RUNNER)],
            cwd=str(REPO),
            stdout=out,
            stderr=err,
            start_new_session=True,
            env=os.environ.copy(),
        )
        print("# westudy_gdrive: spawned weekly runner in background", flush=True)
        return "spawned"
    except Exception as e:
        print(f"# westudy_gdrive spawn failed: {e}", file=sys.stderr)
        out.close()
        err.close()
        return "error"


def portfolio_weekly_needs_catchup() -> bool:
    """今週のフル収集（ログインサイト）が未成功なら True。"""
    if os.environ.get("JARVIS_PORTFOLIO_WEEKLY_DISABLE") == "1":
        return False
    now = datetime.now(JST)
    y, w, _ = now.isocalendar()
    this_week = f"{y}-W{w:02d}"
    if not PORTFOLIO_WEEKLY_STATE.is_file():
        return True
    try:
        data = json.loads(PORTFOLIO_WEEKLY_STATE.read_text(encoding="utf-8"))
    except Exception:
        return True
    if data.get("last_full_iso_week") != this_week:
        return True
    return data.get("last_full_ok") is not True


def spawn_portfolio_weekly(*, dry_run: bool) -> str:
    if not PORTFOLIO_WEEKLY_RUNNER.is_file():
        print(f"# portfolio_weekly: missing {PORTFOLIO_WEEKLY_RUNNER}", file=sys.stderr)
        return "missing"
    if dry_run:
        print("# dry-run: would spawn portfolio_weekly_runner.sh", flush=True)
        return "dry_run"
    PORTFOLIO_LOG_DIR.mkdir(parents=True, exist_ok=True)
    out = open(PORTFOLIO_LOG_DIR / "morning_catchup.out.log", "a", encoding="utf-8")
    err = open(PORTFOLIO_LOG_DIR / "morning_catchup.err.log", "a", encoding="utf-8")
    try:
        out.write(f"\n# spawn {now_iso()}\n")
        out.flush()
        subprocess.Popen(
            ["/bin/zsh", str(PORTFOLIO_WEEKLY_RUNNER)],
            cwd=str(REPO),
            stdout=out,
            stderr=err,
            start_new_session=True,
            env=os.environ.copy(),
        )
        print("# portfolio_weekly: spawned weekly runner in background", flush=True)
        return "spawned"
    except Exception as e:
        print(f"# portfolio_weekly spawn failed: {e}", file=sys.stderr)
        out.close()
        err.close()
        return "error"


def spawn_zaim_csv_weekly(*, dry_run: bool) -> str:
    """週次 CSV をバックグラウンド起動（朝バンドルをブロックしない）。"""
    if not ZAIM_WEEKLY_RUNNER.is_file():
        print(f"# zaim_csv: missing {ZAIM_WEEKLY_RUNNER}", file=sys.stderr)
        return "missing"
    if dry_run:
        print("# dry-run: would spawn zaim_csv_weekly_runner.sh", flush=True)
        return "dry_run"
    ZAIM_LOG_DIR.mkdir(parents=True, exist_ok=True)
    out = open(ZAIM_LOG_DIR / "morning_catchup.out.log", "a", encoding="utf-8")
    err = open(ZAIM_LOG_DIR / "morning_catchup.err.log", "a", encoding="utf-8")
    try:
        out.write(f"\n# spawn {now_iso()}\n")
        out.flush()
        subprocess.Popen(
            ["/bin/zsh", str(ZAIM_WEEKLY_RUNNER)],
            cwd=str(REPO),
            stdout=out,
            stderr=err,
            start_new_session=True,
            env=os.environ.copy(),
        )
        print("# zaim_csv: spawned weekly runner in background", flush=True)
        return "spawned"
    except Exception as e:
        print(f"# zaim_csv spawn failed: {e}", file=sys.stderr)
        out.close()
        err.close()
        return "error"


def upsert_sync_meta(results: dict[str, Any]) -> None:
    """mac_morning_refreshed_at 等を sync_meta へ。"""
    try:
        from supabase import create_client
    except ImportError:
        print("# sync_meta: supabase package missing", file=sys.stderr)
        return
    url = (os.environ.get("JARVIS_SUPABASE_URL") or "").strip()
    key = (os.environ.get("JARVIS_SUPABASE_SERVICE_ROLE_KEY") or "").strip()
    if not url or not key:
        print("# sync_meta: JARVIS_SUPABASE_* 未設定", file=sys.stderr)
        return
    ts = now_iso()
    rows = [
        {"key": "mac_morning_refreshed_at", "value": ts, "updated_at": ts},
        {
            "key": "mac_morning_refresh_ok",
            "value": "1" if results.get("ok") else "0",
            "updated_at": ts,
        },
        {
            "key": "mac_morning_refresh_summary",
            "value": json.dumps(results, ensure_ascii=False)[:1800],
            "updated_at": ts,
        },
    ]
    try:
        sb = create_client(url, key)
        sb.table("sync_meta").upsert(rows, on_conflict="key").execute()
        print(f"# sync_meta: mac_morning_refreshed_at={ts}", flush=True)
    except Exception as e:
        print(f"# sync_meta upsert failed: {e}", file=sys.stderr)


def partner_base() -> Path:
    raw = (os.environ.get("YORITOORI_BASE_PATH") or "").strip()
    if raw:
        return Path(raw).expanduser()
    return (
        Path.home()
        / "Library"
        / "CloudStorage"
        / "OneDrive-個人用"
        / "215_神・大家さん倶楽部"
        / "C2_ルーティン作業"
        / "26_パートナー社への相談"
    )


def main() -> int:
    ap = argparse.ArgumentParser(description="Morning Mac-required refresh bundle")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force", action="store_true", help="同一日の再実行抑制を無視")
    ap.add_argument(
        "--with-line",
        action="store_true",
        help="CHRLINE／オプチャ同期を含める（重い・認証注意）",
    )
    ap.add_argument(
        "--skip-fetch",
        action="store_true",
        help="gmail_to_yoritoori をスキップ",
    )
    ap.add_argument(
        "--skip-push",
        action="store_true",
        help="dashboard_push をスキップ",
    )
    args = ap.parse_args()

    with_line = args.with_line or (
        (os.environ.get("JARVIS_MORNING_WITH_LINE") or "").strip() in ("1", "true", "yes")
    )

    LOG_DIR.mkdir(parents=True, exist_ok=True)

    if not args.force and already_refreshed_today():
        print(f"# skip: already refreshed today ({today_jst()})")
        return 0

    hour = datetime.now(JST).hour
    if not args.force and not (5 <= hour <= 22):
        print(f"# skip: outside daytime window (hour={hour})")
        return 0

    print(f"# morning_mac_refresh start {now_iso()} with_line={with_line}")
    results: dict[str, Any] = {
        "started_at": now_iso(),
        "with_line": with_line,
        "steps": {},
    }
    exe = py_exe()
    failures = 0

    # 1. Web 送信済み → やり取り追記
    rc = run_step(
        "catchup",
        [exe, str(CATCHUP)],
        timeout=180,
        dry_run=args.dry_run,
    )
    results["steps"]["catchup"] = rc
    if rc != 0:
        failures += 1

    # 1b. トリアージ閉じた件の Gmail 既読＋物件紹介 pending 除外
    if GMAIL_READ_CATCHUP.is_file():
        rc = run_step(
            "triage_gmail_read",
            [exe, str(GMAIL_READ_CATCHUP), "--cleanup-re-pending", "--rescue-partner"],
            timeout=300,
            dry_run=args.dry_run,
        )
        results["steps"]["triage_gmail_read"] = rc
        if rc != 0:
            failures += 1
    else:
        results["steps"]["triage_gmail_read"] = "skipped"

    # 2. パートナー Gmail → OneDrive（軽量=通常差分）
    if not args.skip_fetch:
        if GMAIL_SCRIPT.is_file():
            env = os.environ.copy()
            env.setdefault("YORITOORI_BASE_PATH", str(partner_base()))
            rc = run_step(
                "gmail_fetch",
                [exe, str(GMAIL_SCRIPT)],
                cwd=MANUAL_DIR,
                timeout=900,
                dry_run=args.dry_run,
                env=env,
            )
            results["steps"]["gmail_fetch"] = rc
            if rc != 0:
                failures += 1
        else:
            print(f"# gmail_fetch: missing {GMAIL_SCRIPT}", file=sys.stderr)
            results["steps"]["gmail_fetch"] = -1
            failures += 1
    else:
        results["steps"]["gmail_fetch"] = "skipped"

    # 2c. Grok [Grok調査] → KURASHIFT deals（軽量・失敗しても朝バンドルは続行）
    if KURASHIFT_GROK_MATCH.is_file() and not args.skip_fetch:
        rc = run_step(
            "kurashift_grok_mail",
            [exe, str(KURASHIFT_GROK_MATCH), "--grok-only", "--apply"],
            timeout=180,
            dry_run=args.dry_run,
        )
        results["steps"]["kurashift_grok_mail"] = rc
        if rc != 0:
            print(f"# kurashift_grok_mail soft-fail rc={rc}", file=sys.stderr)
    else:
        results["steps"]["kurashift_grok_mail"] = "skipped"

    # 2a. 取込後の新規未返信を partner レーンへ（夜バッチ待ちだとダッシュに出ない）
    night_triage = REPO / "scripts" / "jarvis_night_triage.py"
    if night_triage.is_file():
        rc = run_step(
            "partner_triage_catchup",
            [exe, str(night_triage), "--skip-fetch", "--lane", "partner"],
            timeout=900,
            dry_run=args.dry_run,
        )
        results["steps"]["partner_triage_catchup"] = rc
        if rc != 0:
            print(f"# partner_triage_catchup soft-fail rc={rc}", file=sys.stderr)
    else:
        results["steps"]["partner_triage_catchup"] = "skipped"

    # 2b. Journal／チャット関心 → 要確認アップデート（朝1回・常時監視なし）
    if INTENT_SYNC.is_file():
        rc = run_step(
            "intent_sync",
            [exe, str(INTENT_SYNC), "--pull-journal", "--push"],
            timeout=300,
            dry_run=args.dry_run,
        )
        results["steps"]["intent_sync"] = rc
        # 失敗しても朝バンドル全体は落とさない（負荷・JWT ずれ等）
        if rc != 0:
            print(f"# intent_sync soft-fail rc={rc}", file=sys.stderr)
    else:
        results["steps"]["intent_sync"] = "skipped"

    # 3–4. 状況ウォッチ再集約込みの投影 push（push 内で situation_watch 実行）
    if not args.skip_push:
        rc = run_step(
            "dashboard_push",
            [exe, str(PUSH)],
            timeout=600,
            dry_run=args.dry_run,
        )
        results["steps"]["dashboard_push"] = rc
        if rc != 0:
            failures += 1
    else:
        results["steps"]["dashboard_push"] = "skipped"

    # 4b. Ops Fail ローカル修復キュー（Cloud 上限時の受け皿）
    ops_worker = REPO / "scripts" / "jarvis_ops_fail_local_worker.py"
    if ops_worker.is_file():
        rc = run_step(
            "ops_fail_local",
            [exe, str(ops_worker)],
            timeout=1200,
            dry_run=args.dry_run,
        )
        results["steps"]["ops_fail_local"] = rc
        if rc != 0:
            failures += 1
    else:
        results["steps"]["ops_fail_local"] = "skipped"

    # 5. 任意: CHRLINE／オプチャ
    if with_line:
        if mac_line_running():
            print(
                "# line: Mac版LINE 起動中のためスキップ（トークン保護）",
                file=sys.stderr,
            )
            results["steps"]["line"] = "skipped_mac_line"
        elif RUN_PATCH.is_file():
            rc = run_step(
                "line",
                [
                    str(RUN_PATCH),
                    "chrline_yoritoori_inbox_fetch.py",
                    "--allow-qr-login",
                    "--discover-thread-mids-dry-run",
                ],
                cwd=POC,
                timeout=1800,
                dry_run=args.dry_run,
            )
            results["steps"]["line"] = rc
            if rc != 0:
                failures += 1
            # LINE 後にもう一度投影を揃える
            if not args.skip_push and not args.dry_run and rc == 0:
                rc2 = run_step(
                    "dashboard_push_after_line",
                    [exe, str(PUSH), "--triage-only"],
                    timeout=300,
                    dry_run=False,
                )
                results["steps"]["dashboard_push_after_line"] = rc2
        else:
            print(f"# line: missing {RUN_PATCH}", file=sys.stderr)
            results["steps"]["line"] = -1
            failures += 1
    else:
        results["steps"]["line"] = "skipped"

    # 6. Zaim CSV の取りこぼし（火・金 12:00 失敗／Mac スリープ時のフォールバック）
    if zaim_csv_needs_catchup():
        results["steps"]["zaim_csv_weekly"] = spawn_zaim_csv_weekly(dry_run=args.dry_run)
    else:
        results["steps"]["zaim_csv_weekly"] = "fresh"
        print("# zaim_csv: skip (success within 6 days)", flush=True)

    # 7. WeStudy Drive 添付の取りこぼし（日曜 08:00 失敗／Mac スリープ時）
    if westudy_gdrive_needs_catchup():
        results["steps"]["westudy_gdrive_weekly"] = spawn_westudy_gdrive_weekly(
            dry_run=args.dry_run
        )
    else:
        results["steps"]["westudy_gdrive_weekly"] = "fresh"
        print("# westudy_gdrive: skip (this week's Sunday slot already done)", flush=True)

    # 8. 資産週次（ログインサイト）の取りこぼし
    if portfolio_weekly_needs_catchup():
        results["steps"]["portfolio_weekly"] = spawn_portfolio_weekly(dry_run=args.dry_run)
    else:
        results["steps"]["portfolio_weekly"] = "fresh"
        print("# portfolio_weekly: skip (this week's full collect already done)", flush=True)

    results["ok"] = failures == 0
    results["finished_at"] = now_iso()
    results["failures"] = failures

    if not args.dry_run:
        mark_refreshed_today()
        upsert_sync_meta(results)

    print(
        f"# morning_mac_refresh done ok={results['ok']} failures={failures}",
        flush=True,
    )
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
