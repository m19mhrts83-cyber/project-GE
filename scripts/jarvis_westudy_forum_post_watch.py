#!/usr/bin/env python3
"""Glucon WeStudy 投稿 watch — KeepAlive 常駐。

Dashboard「e-STUDYに投稿」で status=queued になったら、短いポーリング（既定 3秒）
＋ Realtime UPDATE で即ドレインする（2時間待ち／手動 worker 不要）。

  cd ~/git-repos && set -a && source .env.jarvis_private && set +a
  ~/selenium_env/venv/bin/python scripts/jarvis_westudy_forum_post_watch.py
"""
from __future__ import annotations

import atexit
import asyncio
import json
import os
import signal
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PY = Path("/Users/matsunomasaharu2/selenium_env/venv/bin/python")
STATE_PATH = REPO / ".jarvis_state" / "westudy_forum_post_watch.json"
LOCK_PATH = REPO / ".jarvis_state" / "westudy_forum_post_watch.pid"
WORKER = REPO / "scripts" / "jarvis_westudy_forum_post_worker.py"
POLL_SEC = int(os.environ.get("JARVIS_WESTUDY_FORUM_POLL_SEC") or "3")
WAKE_NETWORK_WAIT_SEC = 4
KICK_META_KEY = "westudy_forum_post_kick"

_stop = False
_wake = threading.Event()
_drain_lock = threading.Lock()
_last_kick_seen: str | None = None


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def sb_client():
    from supabase import create_client

    url = (os.environ.get("JARVIS_SUPABASE_URL") or "").strip()
    key = (os.environ.get("JARVIS_SUPABASE_SERVICE_ROLE_KEY") or "").strip()
    if not url or not key:
        return None
    return create_client(url, key)


def write_heartbeat(**extra: object) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "last_heartbeat_at": now_iso(),
        "pid": os.getpid(),
        "mode": "keepalive_poll_plus_realtime",
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
    STATE_PATH.write_text(
        json.dumps(prev, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    try:
        sb = sb_client()
        if sb:
            sb.table("sync_meta").upsert(
                {
                    "key": "westudy_forum_post_watch",
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


def queued_count() -> int:
    sb = sb_client()
    if not sb:
        return 0
    try:
        r = (
            sb.table("glucon_report_drafts")
            .select("id", count="exact")
            .eq("status", "queued")
            .limit(1)
            .execute()
        )
        if getattr(r, "count", None) is not None:
            return int(r.count or 0)
        return len(r.data or [])
    except Exception as e:
        print(f"# queued_count fail: {type(e).__name__}: {e}", flush=True)
        return 0


def kick_meta_changed() -> bool:
    """Dashboard が sync_meta に書いた kick を検知。"""
    global _last_kick_seen
    sb = sb_client()
    if not sb:
        return False
    try:
        r = (
            sb.table("sync_meta")
            .select("value,updated_at")
            .eq("key", KICK_META_KEY)
            .limit(1)
            .execute()
        )
        rows = r.data or []
        if not rows:
            return False
        row = rows[0] or {}
        stamp = str(row.get("updated_at") or row.get("value") or "")
        if not stamp:
            return False
        if _last_kick_seen is None:
            _last_kick_seen = stamp
            return False
        if stamp != _last_kick_seen:
            _last_kick_seen = stamp
            return True
    except Exception as e:
        print(f"# kick_meta skip: {type(e).__name__}: {e}", flush=True)
    return False


def drain_once(*, reason: str = "poll") -> int:
    if not _drain_lock.acquire(blocking=False):
        print(f"# drain skipped (busy) reason={reason}", flush=True)
        return -1
    try:
        n = queued_count()
        if n <= 0 and reason in ("poll", "realtime"):
            write_heartbeat(last_idle_at=now_iso(), queued=0)
            return 0
        print(f"# drain start reason={reason} queued={n}", flush=True)
        py = str(PY if PY.exists() else sys.executable)
        proc = subprocess.run(
            [py, str(WORKER), "--i-confirm-post", "--limit", "5"],
            cwd=str(REPO),
            capture_output=True,
            text=True,
            timeout=1900,
            env=os.environ.copy(),
        )
        out = (proc.stdout or "") + (proc.stderr or "")
        for line in out.splitlines()[-30:]:
            print(line, flush=True)
        write_heartbeat(
            last_drain_at=now_iso(),
            last_drain_exit=proc.returncode,
            last_drain_reason=reason,
            last_drain_queued=n,
            last_drain_tail=out[-1500:],
        )
        return proc.returncode
    finally:
        _drain_lock.release()


def request_drain(reason: str) -> None:
    _wake.reason = reason  # type: ignore[attr-defined]
    _wake.set()


def realtime_thread_main() -> None:
    try:
        asyncio.run(_realtime_async())
    except Exception as e:
        print(f"# realtime thread end: {type(e).__name__}: {e}", flush=True)
        write_heartbeat(realtime=f"end:{type(e).__name__}")


async def _realtime_async() -> None:
    from supabase import create_async_client

    url = (os.environ.get("JARVIS_SUPABASE_URL") or "").strip()
    key = (os.environ.get("JARVIS_SUPABASE_SERVICE_ROLE_KEY") or "").strip()
    if not url or not key:
        write_heartbeat(realtime="skip:no_env")
        return

    sb = await create_async_client(url, key)
    ch = sb.channel("glucon_forum_post_watch")

    def _on_change(_payload: object) -> None:
        print("# realtime change → wake", flush=True)
        request_drain("realtime")

    ch.on_postgres_changes(
        "UPDATE",  # type: ignore[arg-type]
        callback=_on_change,
        schema="public",
        table="glucon_report_drafts",
    )
    ch.on_postgres_changes(
        "INSERT",  # type: ignore[arg-type]
        callback=_on_change,
        schema="public",
        table="glucon_report_drafts",
    )
    await ch.subscribe()
    write_heartbeat(realtime="subscribed")
    print("# realtime subscribed (glucon_report_drafts)", flush=True)
    while not _stop:
        await asyncio.sleep(1)
    try:
        await sb.remove_channel(ch)
    except Exception:
        pass


def on_signal(signum: int, _frame: object) -> None:
    global _stop
    if signum in (signal.SIGTERM, signal.SIGINT):
        print(f"# signal {signum} stop", flush=True)
        _stop = True
        _wake.set()
    elif signum == signal.SIGUSR1:
        print("# SIGUSR1 kick → wake", flush=True)
        request_drain("sigusr1")


def main() -> int:
    global _stop
    signal.signal(signal.SIGTERM, on_signal)
    signal.signal(signal.SIGINT, on_signal)
    try:
        signal.signal(signal.SIGUSR1, on_signal)
    except (ValueError, OSError):
        pass
    acquire_lock()
    atexit.register(release_lock)

    time.sleep(WAKE_NETWORK_WAIT_SEC)
    write_heartbeat(started_at=now_iso(), realtime="starting")
    print(
        f"# westudy forum post watch start pid={os.getpid()} poll={POLL_SEC}s",
        flush=True,
    )
    drain_once(reason="startup")

    rt = threading.Thread(target=realtime_thread_main, name="realtime", daemon=True)
    rt.start()

    next_poll = time.time() + POLL_SEC
    while not _stop:
        timeout = max(0.2, next_poll - time.time())
        woke = _wake.wait(timeout=timeout)
        reason = "poll"
        if woke:
            reason = getattr(_wake, "reason", "wake")
            _wake.clear()
        elif time.time() < next_poll:
            continue
        else:
            if kick_meta_changed():
                reason = "kick_meta"
            elif queued_count() <= 0:
                write_heartbeat()
                next_poll = time.time() + POLL_SEC
                continue
        drain_once(reason=reason)
        write_heartbeat()
        next_poll = time.time() + POLL_SEC
    release_lock()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
