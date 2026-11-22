#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Todoist の朝枠（毎朝 10:30）の排他 — 313 の 0.5（予定タスク todoist-daily-313）と 318 Todoist消化係.

決まり（2026-11-23・318 Phase 3 準備）:
- 朝枠の担当は1つだけ。`.jarvis_state/todoist_morning_owner.json` の owner（無ければ "313" ＝今のまま）
  - 318 の定時実行（--trigger schedule）は owner が "318" の時だけ動く
  - 313 の 0.5 は、移管手順で予定タスクの最初に `check --who 313` を1行足すと、owner が "318" の日・318 実行中は止まる
- 実行中の印 `.jarvis_state/todoist_morning.lock`（O_EXCL）。持っている側がいる間、もう一方は始めない
  - 90 分たったロックは「前回が異常終了」とみなして外してよい（pid が生きていれば外さない）
- 313 の 0.5 は今はロックを取らないので、318 側は 313 の作業跡（当日 90 分以内の /tmp/t313_pending.json）も見る

  python3 scripts/jarvis_todoist_morning_slot.py status
  python3 scripts/jarvis_todoist_morning_slot.py check --who 313     # 0=動いてよい / 3=止める（理由を表示）
  python3 scripts/jarvis_todoist_morning_slot.py set-owner --who 318 --yes   # 移管の時だけ（松野さん了承後）
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

REPO = Path(__file__).resolve().parents[1]
JST = ZoneInfo("Asia/Tokyo")
WHO = ("313", "318")
DEFAULT_OWNER = "313"
STALE_MIN = 90
T313_PENDING = Path("/tmp/t313_pending.json")  # 313 0.5 の手順1が書く作業ファイル


class SlotBusy(Exception):
    def __init__(self, code: str, reason: str):
        super().__init__(reason)
        self.code = code
        self.reason = reason


def _now() -> datetime:
    return datetime.now(JST)


def owner_path(state_dir: Path) -> Path:
    return state_dir / "todoist_morning_owner.json"


def lock_path(state_dir: Path) -> Path:
    return state_dir / "todoist_morning.lock"


def get_owner(state_dir: Path) -> str:
    """朝枠の担当。ファイルが無ければ 313（今のまま）。壊れていたら例外（推測で担当を決めない）。"""
    p = owner_path(state_dir)
    if not p.is_file():
        return DEFAULT_OWNER
    d = json.loads(p.read_text(encoding="utf-8"))
    who = str(d.get("owner") or "")
    if who not in WHO:
        raise ValueError(f"朝枠の担当が想定外: {who!r}")
    return who


def set_owner(state_dir: Path, who: str, *, by: str = "manual") -> None:
    if who not in WHO:
        raise ValueError(who)
    p = owner_path(state_dir)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps({"owner": who, "since": _now().isoformat(timespec="seconds"), "by": by},
                              ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, p)


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def read_lock(state_dir: Path) -> dict | None:
    p = lock_path(state_dir)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {"who": "?", "broken": True}


def lock_is_stale(info: dict, now: datetime) -> bool:
    try:
        at = datetime.fromisoformat(str(info.get("started_at") or ""))
    except ValueError:
        return False
    return now - at > timedelta(minutes=STALE_MIN) and not _pid_alive(int(info.get("pid") or 0))


def t313_signal(now: datetime, path: Path = T313_PENDING) -> bool:
    """313 0.5 が今まさに動いている跡（90 分以内に書かれた作業ファイル）。"""
    try:
        mt = datetime.fromtimestamp(path.stat().st_mtime, JST)
    except OSError:
        return False
    return now - mt <= timedelta(minutes=STALE_MIN)


def acquire(state_dir: Path, who: str, run_id: str, *, now: datetime | None = None, pid: int | None = None) -> None:
    now = now or _now()
    p = lock_path(state_dir)
    p.parent.mkdir(parents=True, exist_ok=True)
    body = json.dumps({"who": who, "run_id": run_id, "pid": pid or os.getpid(), "started_at": now.isoformat(timespec="seconds")})
    for _ in range(2):
        try:
            fd = os.open(p, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            info = read_lock(state_dir) or {}
            if not info.get("broken") and lock_is_stale(info, now):
                p.unlink(missing_ok=True)  # 前回が異常終了（90 分超・pid なし）
                continue
            raise SlotBusy("morning_busy", f"朝枠を {info.get('who', '?')} が使用中（{info.get('started_at', '?')}）")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(body)
        return
    raise SlotBusy("morning_busy", "朝枠のロックを取れない")


def release(state_dir: Path, run_id: str) -> None:
    info = read_lock(state_dir)
    if info and info.get("run_id") == run_id:
        lock_path(state_dir).unlink(missing_ok=True)


def check(state_dir: Path, who: str, *, scheduled: bool, now: datetime | None = None,
          t313_path: Path | None = None) -> tuple[str, str]:
    """動いてよければ ("", "")、止めるなら (code, 理由)。scheduled=True は定時起動（担当の時だけ動く）。

    code: owner_unreadable（担当ファイルが壊れている）／not_owner（担当でない＝正常に見送り）／busy（相手が使用中）
    """
    now = now or _now()
    try:
        owner = get_owner(state_dir)
    except Exception as e:  # noqa: BLE001
        return "owner_unreadable", f"朝枠の担当ファイルが読めない（{type(e).__name__}）。推測で動かない"
    if scheduled and owner != who:
        return "not_owner", f"朝枠の担当は {owner}（{who} の定時実行はしない）"
    info = read_lock(state_dir)
    if info and info.get("who") != who and (info.get("broken") or not lock_is_stale(info, now)):
        return "busy", f"朝枠を {info.get('who', '?')} が使用中"
    if who == "318" and t313_signal(now, t313_path or T313_PENDING):
        return "busy", "313 の 0.5 が動いている跡がある（90 分以内の作業ファイル）"
    return "", ""


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--state-dir", default=str(REPO / ".jarvis_state"))
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status")
    c = sub.add_parser("check")
    c.add_argument("--who", choices=WHO, required=True)
    c.add_argument("--manual", action="store_true", help="手動の実行（担当でなくてもよい。使用中なら止める）")
    o = sub.add_parser("set-owner")
    o.add_argument("--who", choices=WHO, required=True)
    o.add_argument("--yes", action="store_true", help="移管の手順どおりに確かめた時だけ")
    a = ap.parse_args(argv)
    sd = Path(a.state_dir).expanduser()
    if a.cmd == "status":
        try:
            owner = get_owner(sd)
        except Exception as e:  # noqa: BLE001
            owner = f"読めない（{type(e).__name__}）"
        print(f"owner={owner} lock={read_lock(sd) or 'なし'} t313_signal={t313_signal(_now())}")
        return 0
    if a.cmd == "check":
        code, why = check(sd, a.who, scheduled=not a.manual)
        if code:
            print(f"STOP: {why}")
            return 3
        print("OK")
        return 0
    if a.cmd == "set-owner":
        if not a.yes:
            print("--yes が要る（移管手順 318_Todoist消化係/移管手順_10時30分.md を確かめてから）", file=sys.stderr)
            return 2
        set_owner(sd, a.who)
        print(f"朝枠の担当を {a.who} にした")
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
