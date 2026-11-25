#!/usr/bin/env python3
"""Vポイント Tサイト履歴の定期取得（毎月24日朝・窓C前日）の包み役（614・2026-11-25）。

本体の取得は scripts/jarvis_vpoint_tsite_fetch.py（V会員番号＋メールOTP。OTP は Gmail API が読む）。
ここは次の4点だけを足す。取得そのものは変えない。
  1. 停止スイッチ JARVIS_VPOINT_TSITE_FETCH_DISABLE=1
  2. 1日1回ガード（成功済み・試行上限の日は何もしない）。再試行は1日1回まで（最初＋再試行1回）
  3. OTP が届かない・認証が通らない時は「認証待ち」として止まる（再試行しない＝OTP メールを増やさない）
  4. 止まった時は #ops に1日1回だけ知らせる。定例（jarvis_vpoint_routine.py）は壊さない
成功の判定は「終了コード0」かつ「当日分の履歴ファイルを読み戻せた」こと。

Mac がスリープで朝に動かなかった時は、launchd の StartCalendarInterval が復帰時に1回実行する
（既存の時刻指定ジョブと同じ。新しい常駐は作らない）。

使い方:
  python scripts/jarvis_vpoint_tsite_scheduled.py            # 本番（launchd ランナーから）
  python scripts/jarvis_vpoint_tsite_scheduled.py --dry-run  # 取得せず、何をするかだけ表示
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
STATE_DIR = REPO / ".jarvis_state"
RUN_STATE = STATE_DIR / "vpoint_tsite_fetch_run.json"
HISTORY_PREFIX = "vpoint_tsite_history_"
FETCH_SCRIPT = REPO / "scripts" / "jarvis_vpoint_tsite_fetch.py"
SLACK_POST = REPO / "scripts" / "jarvis_slack_webhook_post.py"
PRIVATE_ENV = REPO / ".env.jarvis_private"

MAX_ATTEMPTS = 2  # 最初の1回＋再試行1回（1日あたり）
RETRY_WAIT_SEC = 600
FETCH_TIMEOUT_SEC = 600

# tsite_fetch.py が出す、認証まわりで止まった時の文言
AUTH_WAIT_MARKERS = (
    "OTP を取得できませんでした",
    "ログイン未完了のまま",
    "本人認証",
)


def now_jst() -> datetime:
    return datetime.now(JST)


def load_dotenv(path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    if not path.is_file():
        return env
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def disabled(env: dict[str, str]) -> bool:
    v = os.environ.get("JARVIS_VPOINT_TSITE_FETCH_DISABLE") or env.get(
        "JARVIS_VPOINT_TSITE_FETCH_DISABLE", ""
    )
    return v.strip() == "1"


def load_state(path: Path | None = None) -> dict[str, Any]:
    path = path or RUN_STATE
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def save_state(state: dict[str, Any], path: Path | None = None) -> None:
    path = path or RUN_STATE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def should_run(state: dict[str, Any], today: str) -> tuple[bool, str]:
    """今日これ以上取りに行くか。(行く?, 理由)"""
    if state.get("date") != today:
        return True, "new_day"
    if state.get("status") == "ok":
        return False, "already_ok_today"
    if state.get("status") == "auth_wait":
        return False, "auth_wait_today"
    if int(state.get("attempts") or 0) >= MAX_ATTEMPTS:
        return False, "attempts_exhausted"
    return True, "retry_today"


def classify_failure(returncode: int | None, output: str, timed_out: bool) -> str:
    """'auth_wait'（認証待ち・再試行しない）か 'failed'（再試行の対象）。"""
    if not timed_out and any(m in output for m in AUTH_WAIT_MARKERS):
        return "auth_wait"
    return "failed"


def history_readback_ok(today: str, state_dir: Path | None = None) -> bool:
    """当日分の履歴ファイルを読み戻し、取得日が今日で、行か残高があること。"""
    state_dir = state_dir or STATE_DIR
    path = state_dir / f"{HISTORY_PREFIX}{today.replace('-', '')}.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    if not str(data.get("fetched_at") or "").startswith(today):
        return False
    return bool(data.get("key_entries")) or data.get("balance_pt") is not None


def ops_text(status: str, today: str, attempts: int) -> str:
    if status == "auth_wait":
        head = "【ops】Vポイント Tサイト履歴の定期取得が認証待ちで止まりました"
        sig = "判定: 🟡 認証待ち（確認コードが届かない／認証が通らない）"
        nxt = "次の手: 松野さんが『Tサイト取って』で取り直す（コードは本人メールを読むだけ）"
    else:
        head = "【ops】Vポイント Tサイト履歴の定期取得に失敗しました"
        sig = f"判定: 🔴 失敗（{attempts}回試して取れず）"
        nxt = "次の手: 窓C（25日〜）の付与サマリは部分成功のまま。『Tサイト取って』で取り直す"
    return (
        f"{head}\n{sig}\n日付: {today}\n{nxt}\n"
        "ログ: ~/Library/Logs/jarvis_vpoint_tsite_fetch/"
    )


def post_ops(text: str) -> bool:
    """#ops に1回。失敗しても本体は止めない。"""
    try:
        r = subprocess.run(
            [sys.executable, str(SLACK_POST), "--channel", "ops", "--text", text],
            cwd=str(REPO),
            timeout=60,
            capture_output=True,
            text=True,
        )
        return r.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def run_fetch() -> tuple[int | None, str, bool]:
    """tsite_fetch.py を1回。(終了コード, 出力の末尾, タイムアウトか)。出力に実額が混じるので呼び出し側はログに出さない。"""
    try:
        r = subprocess.run(
            [sys.executable, "-u", str(FETCH_SCRIPT)],
            cwd=str(REPO),
            timeout=FETCH_TIMEOUT_SEC,
            capture_output=True,
            text=True,
        )
        return r.returncode, (r.stdout or "") + (r.stderr or ""), False
    except subprocess.TimeoutExpired:
        return None, "", True
    except OSError as exc:
        return None, str(exc), False


def log(msg: str) -> None:
    print(f"{now_jst().strftime('%Y-%m-%d %H:%M:%S %z')} {msg}", flush=True)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Tサイト履歴の定期取得（窓C前日）")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--retry-wait-sec", type=int, default=RETRY_WAIT_SEC)
    args = ap.parse_args(argv)

    env = load_dotenv(PRIVATE_ENV)
    if disabled(env):
        log("停止: JARVIS_VPOINT_TSITE_FETCH_DISABLE=1")
        return 0

    today = now_jst().strftime("%Y-%m-%d")
    state = load_state()
    go, why = should_run(state, today)
    if not go:
        log(f"skip: {why}")
        return 0
    if args.dry_run:
        log(f"dry-run: 取得する予定（{why}）")
        return 0

    attempts = int(state.get("attempts") or 0) if state.get("date") == today else 0
    status = "failed"
    while attempts < MAX_ATTEMPTS:
        attempts += 1
        log(f"取得 {attempts}/{MAX_ATTEMPTS}")
        rc, out, timed_out = run_fetch()
        if rc == 0 and history_readback_ok(today):
            status = "ok"
            log("OK: 当日分の履歴を読み戻せた")
            break
        status = classify_failure(rc, out, timed_out)
        # 出力には実額が混じり得る。ログには終了コードと分類だけ書く
        log(f"NG: exit={rc} timeout={timed_out} → {status}")
        if status == "auth_wait":
            break
        if attempts < MAX_ATTEMPTS:
            time.sleep(max(0, args.retry_wait_sec))

    new_state: dict[str, Any] = {
        "date": today,
        "attempts": attempts,
        "status": status,
        "updated_at": now_jst().isoformat(timespec="seconds"),
        "ops_notified": bool(state.get("ops_notified")) if state.get("date") == today else False,
    }
    if status == "ok":
        new_state["last_ok_at"] = new_state["updated_at"]
    else:
        new_state["last_ok_at"] = state.get("last_ok_at")
        if not new_state["ops_notified"]:
            new_state["ops_notified"] = post_ops(ops_text(status, today, attempts))
            log(f"#ops 通知: {'送信' if new_state['ops_notified'] else '送れず'}")
    save_state(new_state)
    return 0 if status == "ok" else 1


if __name__ == "__main__":
    sys.exit(main())
