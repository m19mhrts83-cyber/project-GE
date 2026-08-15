#!/usr/bin/env python3
"""KURASHIFT job watch — KeepAlive 常駐。

本線: 30秒ポーリングで queued をドレイン。
加速: Supabase Realtime（publication 済み時のみ・失敗しても落ちない）。
起動／再接続時は即ドレイン。heartbeat を .jarvis_state に書く。

  cd ~/git-repos && set -a && source .env.jarvis_private && set +a
  ~/selenium_env/venv/bin/python scripts/jarvis_kurashift_job_watch.py
"""
from __future__ import annotations

import atexit
import json
import os
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PY = Path("/Users/matsunomasaharu2/selenium_env/venv/bin/python")
STATE_PATH = REPO / ".jarvis_state" / "kurashift_job_watch.json"
LOCK_PATH = REPO / ".jarvis_state" / "kurashift_job_watch.pid"
WORKER = REPO / "scripts" / "jarvis_kurashift_job_worker.py"
POLL_SEC = 30
DRAIN_LIMIT = 8
WAKE_NETWORK_WAIT_SEC = 4

_stop = False


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def write_heartbeat(**extra: object) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "last_heartbeat_at": now_iso(),
        "pid": os.getpid(),
        "mode": "keepalive_poll",
        "poll_sec": POLL_SEC,
        **extra,
    }
    prev: dict = {}
    if STATE_PATH.is_file():
        try:
            prev = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        except Exception:
            prev = {}
    prev.update(payload)
    STATE_PATH.write_text(json.dumps(prev, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    # Vercel UI 用に DB にも投影（ファイルは Mac ローカルのみ）
    try:
        from supabase import create_client

        url = (os.environ.get("JARVIS_SUPABASE_URL") or "").strip()
        key = (os.environ.get("JARVIS_SUPABASE_SERVICE_ROLE_KEY") or "").strip()
        if url and key:
            sb = create_client(url, key)
            sb.table("sync_meta").upsert(
                {
                    "key": "kurashift_job_watch",
                    "value": json.dumps(prev, ensure_ascii=False),
                    "updated_at": now_iso(),
                }
            ).execute()
    except Exception as e:
        print(f"# heartbeat db skip: {type(e).__name__}: {e}", flush=True)


def acquire_lock() -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    if LOCK_PATH.is_file():
        try:
            old = int(LOCK_PATH.read_text(encoding="utf-8").strip() or "0")
        except ValueError:
            old = 0
        if old and old != os.getpid():
            try:
                os.kill(old, 0)
            except OSError:
                pass
            else:
                raise SystemExit(f"another watch running pid={old}")
    LOCK_PATH.write_text(str(os.getpid()), encoding="utf-8")


def release_lock() -> None:
    try:
        if LOCK_PATH.is_file() and LOCK_PATH.read_text(encoding="utf-8").strip() == str(
            os.getpid()
        ):
            LOCK_PATH.unlink()
    except OSError:
        pass


def drain_once() -> int:
    py = str(PY if PY.exists() else sys.executable)
    env = os.environ.copy()
    proc = subprocess.run(
        [py, str(WORKER), "--limit", str(DRAIN_LIMIT)],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        timeout=1900,
        env=env,
    )
    out = (proc.stdout or "") + (proc.stderr or "")
    for line in out.splitlines()[-20:]:
        print(line, flush=True)
    write_heartbeat(
        last_drain_at=now_iso(),
        last_drain_exit=proc.returncode,
        last_drain_tail=out[-1500:],
    )
    return proc.returncode


def try_realtime_loop() -> None:
    """任意加速。失敗したらすぐ戻ってポーリング本線へ。"""
    try:
        from supabase import create_client
    except Exception as e:
        print(f"# realtime unavailable: {type(e).__name__}: {e}", flush=True)
        return

    url = (os.environ.get("JARVIS_SUPABASE_URL") or "").strip()
    key = (os.environ.get("JARVIS_SUPABASE_SERVICE_ROLE_KEY") or "").strip()
    if not url or not key:
        return

    try:
        sb = create_client(url, key)
        # supabase-py realtime API は版差が大きい。subscribe できなければ無視。
        channel = sb.channel("kurashift_jobs_watch")

        def _on_insert(payload: dict) -> None:  # noqa: ARG001
            print("# realtime insert → drain", flush=True)
            time.sleep(0.5)
            drain_once()

        # 新しめのクライアント想定（無ければ except）
        channel.on_postgres_changes(
            "INSERT",
            schema="public",
            table="kurashift_jobs",
            callback=_on_insert,
        )
        channel.subscribe()
        write_heartbeat(realtime="subscribed")
        print("# realtime subscribed (accel)", flush=True)
        while not _stop:
            time.sleep(1)
    except Exception as e:
        print(f"# realtime skip: {type(e).__name__}: {e}", flush=True)
        write_heartbeat(realtime=f"skip:{type(e).__name__}")


def on_signal(signum: int, _frame: object) -> None:
    global _stop
    print(f"# signal {signum} stop", flush=True)
    _stop = True


def main() -> int:
    global _stop
    signal.signal(signal.SIGTERM, on_signal)
    signal.signal(signal.SIGINT, on_signal)
    acquire_lock()
    atexit.register(release_lock)

    # 起床直後の DNS 待ち
    time.sleep(WAKE_NETWORK_WAIT_SEC)
    write_heartbeat(started_at=now_iso())
    print(f"# kurashift job watch start pid={os.getpid()} poll={POLL_SEC}s", flush=True)
    drain_once()

    # Realtime は別スレッドで試すが、本線はポーリング（簡易: 同期ポーリングのみ）
    # ※ Realtime の安定版差を避けるため、本実装はポーリング本線に寄せる。
    next_poll = 0.0
    while not _stop:
        now = time.time()
        if now >= next_poll:
            drain_once()
            write_heartbeat()
            next_poll = time.time() + POLL_SEC
        time.sleep(1)
    release_lock()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
