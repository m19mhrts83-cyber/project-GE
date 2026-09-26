#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""画面ロック解除で、間隔ポーリング系の launchd を1回走らせる。

入口: macOS 通知 com.apple.screenIsUnlocked（スリープ後のロック解除を含む）
確認: 解除のたびに下の RUNNERS だけ。時刻指定ジョブは起動しない
履歴: ~/Library/Logs/jarvis_screen_unlock/catchup.log
停止: JARVIS_SCREEN_UNLOCK_CATCHUP_DISABLE=1 のあと launchd を入れ直す
      または launchd/uninstall_screen_unlock_catchup_launchd.sh

時刻指定（Zaim・週次・朝定時）は、スリープで時刻を逃すと macOS が
復帰時に1回実行する。ロック解除のたびにそこへは足さない。
"""
from __future__ import annotations

import ctypes
import os
import select
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
LOG_DIR = Path.home() / "Library" / "Logs" / "jarvis_screen_unlock"
LOG_PATH = LOG_DIR / "catchup.log"

# 15分間隔クラス。常駐（KeepAlive）や 45秒ワーカーは対象外。
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
