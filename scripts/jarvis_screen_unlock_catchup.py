#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""画面ロック解除で、間隔ポーリング系の launchd を1回走らせる。

入口: macOS 通知 com.apple.screenIsUnlocked（スリープ後のロック解除を含む）
確認: 解除のたびに下の RUNNERS だけ。時刻指定ジョブは原則起動しない
例外: 111 夜枠（20:30以降・未実施）だけ「Macを開いたとき」回収（計画どおり）
履歴: ~/Library/Logs/jarvis_screen_unlock/catchup.log
停止: JARVIS_SCREEN_UNLOCK_CATCHUP_DISABLE=1 のあと launchd を入れ直す
      または launchd/uninstall_screen_unlock_catchup_launchd.sh

時刻指定（Zaim・週次・朝定時）は、スリープで時刻を逃すと macOS が
復帰時に1回実行する。ロック解除のたびにそこへは足さない（111夜以外）。
"""
from __future__ import annotations

import ctypes
import json
import os
import select
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

REPO = Path(__file__).resolve().parents[1]
LOG_DIR = Path.home() / "Library" / "Logs" / "jarvis_screen_unlock"
LOG_PATH = LOG_DIR / "catchup.log"
JST = ZoneInfo("Asia/Tokyo")
PARTNER_111_NIGHT_STATE = REPO / ".jarvis_state" / "partner_111_night.json"
PARTNER_111_NIGHT_RUNNER = REPO / "launchd" / "partner_111_night_runner.sh"

# 15分間隔クラス。常駐（KeepAlive）や 45秒ワーカーは対象外。
# bucho_inbox_poll_runner 内で calendar_sync / watch_todoist_sync も走る。
RUNNERS = (
    "launchd/bucho_inbox_poll_runner.sh",
    "launchd/todoist_comment_inbox_runner.sh",
)

NOTIFY_NAME = b"com.apple.screenIsUnlocked"
STARTUP_GRACE_SEC = 120
DEBOUNCE_SEC = 90
RUN_TIMEOUT_SEC = 900


def _log(msg: str) -> None:
    line = f"{time.strftime('%Y-%m-%d %H:%M:%S %z')} {msg}"
    print(line, flush=True)
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        with LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError as exc:
        print(f"log skip: {exc}", file=sys.stderr, flush=True)


def _disabled() -> bool:
    return (os.environ.get("JARVIS_SCREEN_UNLOCK_CATCHUP_DISABLE") or "").strip() == "1"


def _register_fd() -> int:
    lib = ctypes.CDLL("/usr/lib/libSystem.B.dylib")
    fn = lib.notify_register_file_descriptor
    fn.argtypes = [
        ctypes.c_char_p,
        ctypes.POINTER(ctypes.c_int),
        ctypes.c_int,
        ctypes.POINTER(ctypes.c_int),
    ]
    fn.restype = ctypes.c_uint32
    fd = ctypes.c_int(-1)
    token = ctypes.c_int(0)
    status = fn(NOTIFY_NAME, ctypes.byref(fd), 0, ctypes.byref(token))
    if status != 0 or fd.value < 0:
        raise RuntimeError(f"notify_register_file_descriptor failed: {status}")
    os.set_blocking(fd.value, False)
    return fd.value


def _drain(fd: int) -> None:
    while True:
        try:
            chunk = os.read(fd, 64)
        except BlockingIOError:
            return
        if not chunk:
            return


def _partner_111_night_due() -> bool:
    """20:30 JST 以降かつ今夜未実施なら True。"""
    if (os.environ.get("JARVIS_PARTNER_111_NIGHT_DISABLE") or "").strip() in (
        "1",
        "true",
        "yes",
    ):
        return False
    now = datetime.now(JST)
    if (now.hour, now.minute) < (20, 30):
        return False
    today = now.strftime("%Y-%m-%d")
    if not PARTNER_111_NIGHT_STATE.is_file():
        return True
    try:
        data = json.loads(PARTNER_111_NIGHT_STATE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return True
    # 今夜すでに試行済み（失敗含む）なら回収しない（重複起動で QR・ダッシュボードが何度も出るため）
    return today not in (data.get("last_ok_date"), data.get("last_attempt_date"))


def _maybe_partner_111_night() -> None:
    if not _partner_111_night_due():
        return
    if not PARTNER_111_NIGHT_RUNNER.is_file():
        _log("missing partner_111_night_runner.sh")
        return
    _log("start partner_111_night (20:30窓・未実施)")
    try:
        proc = subprocess.run(
            ["/bin/zsh", str(PARTNER_111_NIGHT_RUNNER)],
            cwd=str(REPO),
            timeout=RUN_TIMEOUT_SEC,
            check=False,
        )
        _log(f"end partner_111_night exit={proc.returncode}")
    except subprocess.TimeoutExpired:
        _log("timeout partner_111_night")
    except OSError as exc:
        _log(f"fail partner_111_night: {exc}")


def _run_catchup() -> None:
    for rel in RUNNERS:
        path = REPO / rel
        if not path.is_file():
            _log(f"missing {rel}")
            continue
        _log(f"start {rel}")
        try:
            proc = subprocess.run(
                ["/bin/zsh", str(path)],
                cwd=str(REPO),
                timeout=RUN_TIMEOUT_SEC,
                check=False,
            )
            _log(f"end {rel} exit={proc.returncode}")
        except subprocess.TimeoutExpired:
            _log(f"timeout {rel}")
        except OSError as exc:
            _log(f"fail {rel}: {exc}")
    _maybe_partner_111_night()


def main() -> int:
    if _disabled():
        _log("停止: JARVIS_SCREEN_UNLOCK_CATCHUP_DISABLE=1")
        return 0
    try:
        fd = _register_fd()
    except Exception as exc:
        _log(f"ERROR: {exc}")
        return 1
    started = time.time()
    last_run = 0.0
    _log("listening com.apple.screenIsUnlocked")
    while True:
        ready, _, _ = select.select([fd], [], [], 3600)
        if not ready:
            continue
        _drain(fd)
        now = time.time()
        if now - started < STARTUP_GRACE_SEC:
            _log("skip startup grace")
            continue
        if now - last_run < DEBOUNCE_SEC:
            _log("skip debounce")
            continue
        last_run = now
        _log("unlock → interval catchup")
        _run_catchup()


if __name__ == "__main__":
    raise SystemExit(main())
