#!/usr/bin/env python3
"""614 ポイント・還元ウォッチ — #ops 障害通知の土台（P1・工程20）。

  notify_ops      工程・原因・次の対応・run_id を #ops へ。送れなければ非公開側（pending）へ保存
  flush_pending   保留中の通知を再送（全体停止 OFF の次回起動で）。1通あたり最大 MAX_ATTEMPTS 回
  emergency_log   主保存先（.jarvis_state）とは別の場所の緊急ログ。主保存先が壊れても残す
  global_stop     全体停止スイッチ（JARVIS_614_GLOBAL_STOP=1 または 614_watch/GLOBAL_STOP ファイル）

再帰・ループの防止:
  - 通知の送信中は JARVIS_614_OPS_ACTIVE=1 を子に渡し、通知の失敗からさらに通知を作らない
  - 通知の失敗は pending → 緊急ログの順に残すだけ（#ops への再通知は作らない）
  - 同じ障害（系統＋工程＋原因）は同じ日に1回だけ送る
全体停止中は新しい通知も保留の再送も送らない（pending に積むだけ）。
秘密・実額は書かない（呼び出し側が原因文に入れない）。
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Callable
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent))
import jarvis_614_runlog as runlog  # noqa: E402

JST = ZoneInfo("Asia/Tokyo")
REPO = Path(__file__).resolve().parents[1]
POST = REPO / "scripts" / "jarvis_slack_webhook_post.py"
MAX_ATTEMPTS = 5
MAX_FLUSH_PER_RUN = 5
_TRUE = ("1", "true", "yes", "on")


def global_stop() -> bool:
    if (os.environ.get("JARVIS_614_GLOBAL_STOP") or "").strip().lower() in _TRUE:
        return True
    try:
        return (runlog.log_dir() / "GLOBAL_STOP").exists()
    except OSError as e:
        emergency_log(f"全体停止の印を読めず安全側で停止扱い（{type(e).__name__}）")
        return True  # 読めない時は安全側（止める）。緊急ログに残して無言にしない


def _guard_active() -> bool:
    return (os.environ.get("JARVIS_614_OPS_ACTIVE") or "").strip() == "1"


def pending_path() -> Path:
    return runlog.log_dir() / "ops_pending.jsonl"


def emergency_dir() -> Path:
    env = (os.environ.get("JARVIS_614_EMERGENCY_DIR") or "").strip()
    return Path(env).expanduser() if env else Path.home() / "Library" / "Logs" / "jarvis_614"


def emergency_log(line: str) -> bool:
    """主保存先とは別の領域へ1行。どんな失敗でも例外を投げない。"""
    try:
        d = emergency_dir()
        d.mkdir(parents=True, exist_ok=True)
        with open(d / "emergency.log", "a", encoding="utf-8") as f:
            f.write(f"{runlog.now_iso()} {line[:400]}\n")
        return True
    except OSError:
        return False


def _append_jsonl(path: Path, rec: dict[str, Any]) -> bool:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            os.write(fd, (json.dumps(rec, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8"))
            os.fsync(fd)
        finally:
            os.close(fd)
        return True
    except OSError:
        return False


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    try:
        for ln in path.read_text(encoding="utf-8").splitlines():
            try:
                d = json.loads(ln)
            except json.JSONDecodeError:
                continue
            if isinstance(d, dict):
                out.append(d)
    except OSError:
        pass
    return out


def compose(*, system: str, stage: str, cause: str, next_action: str, run_id: str) -> str:
    return "\n".join(
        [
            "【614 ポイント還元｜障害】",
            f"・系統/工程: {system} / {stage}",
            f"・原因: {cause}",
            f"・次の対応: {next_action}",
            f"・run: {run_id}",
        ]
    )


def notification_id(system: str, stage: str, cause: str, day: str) -> str:
    return hashlib.sha256(f"{system}|{stage}|{cause}|{day}".encode()).hexdigest()[:16]


def _default_poster(text: str) -> int:
    """#ops へ送る。0=送信できた。それ以外は未送信または結果不明（どちらも pending に積む）。"""
    env = os.environ.copy()
    env["JARVIS_614_OPS_ACTIVE"] = "1"
    try:
        return subprocess.run(
            [sys.executable, str(POST), "--channel", "ops", "--text", text],
            cwd=str(REPO), env=env, check=False, timeout=60,
        ).returncode
    except (OSError, subprocess.SubprocessError):
        return 1


def _pending_state() -> dict[str, dict[str, Any]]:
    """id ごとの最新状態（追記ログの最後の行）。"""
    state: dict[str, dict[str, Any]] = {}
    for r in _read_jsonl(pending_path()):
        if r.get("id"):
            state[str(r["id"])] = r
    return state


def enqueue_pending(text: str, *, nid: str, system: str, stage: str, run_id: str) -> bool:
    rec = {
        "id": nid, "status": "pending", "text": text, "system": system, "stage": stage,
        "run_id": run_id, "queued_at": runlog.now_iso(), "attempts": 0,
    }
    ok = _append_jsonl(pending_path(), rec)
    if not ok:
        emergency_log(f"ops_pending 書込失敗 id={nid} {system}/{stage} run={run_id}")
    return ok


def notify_ops(
    *, system: str, stage: str, cause: str, next_action: str, run_id: str,
    dry_run: bool = False, poster: Callable[[str], int] | None = None,
) -> dict[str, Any]:
    """障害を #ops へ。返り値: {"status": sent|queued|duplicate|stopped|guard|dry_run|lost}。"""
    text = compose(system=system, stage=stage, cause=cause, next_action=next_action, run_id=run_id)
    if dry_run:
        print("--- ops (dry-run・未配信) ---\n" + text + "\n---")
        return {"status": "dry_run"}
    if _guard_active():
        # 通知の送信中に起きた失敗からは通知を作らない（ループ防止）。緊急ログだけ
        emergency_log(f"ops 再帰を抑止 {system}/{stage}: {cause[:120]}")
        return {"status": "guard"}
    day = datetime.now(JST).strftime("%Y-%m-%d")
    nid = notification_id(system, stage, cause, day)
    st = _pending_state().get(nid)
    if st is not None:
        return {"status": "duplicate", "id": nid}  # 同じ障害は同じ日に1回
    if global_stop():
        queued = enqueue_pending(text, nid=nid, system=system, stage=stage, run_id=run_id)
        return {"status": "stopped" if queued else "lost", "id": nid}
    rc = (poster or _default_poster)(text)
    if rc == 0:
        _append_jsonl(pending_path(), {"id": nid, "status": "sent", "system": system, "stage": stage,
                                       "run_id": run_id, "sent_at": runlog.now_iso()})
        return {"status": "sent", "id": nid}
    queued = enqueue_pending(text, nid=nid, system=system, stage=stage, run_id=run_id)
    if not queued:
        emergency_log(f"ops 通知を送れず保存も失敗 {system}/{stage}: {cause[:120]} run={run_id}")
    return {"status": "queued" if queued else "lost", "id": nid}


def flush_pending(*, poster: Callable[[str], int] | None = None, limit: int = MAX_FLUSH_PER_RUN) -> dict[str, Any]:
    """保留中の通知を再送。全体停止中・通知送信中は何もしない。履歴は消さず、結果を追記する。"""
    out = {"sent": 0, "failed": 0, "gave_up": 0, "skipped": ""}
    if global_stop():
        out["skipped"] = "global_stop"
        return out
    if _guard_active():
        out["skipped"] = "guard"
        return out
    todo = [r for r in _pending_state().values() if r.get("status") == "pending"]
    todo.sort(key=lambda r: str(r.get("queued_at")))
    for r in todo[:limit]:
        attempts = int(r.get("attempts") or 0) + 1
        rc = (poster or _default_poster)(str(r.get("text") or ""))
        base = {k: r.get(k) for k in ("id", "system", "stage", "run_id", "text", "queued_at")}
        if rc == 0:
            _append_jsonl(pending_path(), {**base, "status": "sent", "attempts": attempts, "sent_at": runlog.now_iso()})
            out["sent"] += 1
        elif attempts >= MAX_ATTEMPTS:
            _append_jsonl(pending_path(), {**base, "status": "gave_up", "attempts": attempts})
            emergency_log(f"ops 通知を {MAX_ATTEMPTS} 回送れず保留のまま id={r.get('id')} {r.get('system')}/{r.get('stage')}")
            out["gave_up"] += 1
        else:
            _append_jsonl(pending_path(), {**base, "status": "pending", "attempts": attempts})
            out["failed"] += 1
    return out
