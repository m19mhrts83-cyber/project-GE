#!/usr/bin/env python3
"""614 ポイント・還元ウォッチ — run の集約記録（P1・工程31）。

1 run ＝ スクリプト1回の起動。run → 系統（teiki / etc / vpoint / card_benefit）→ 工程（fetch / save /
save_verify / stamp / push / display / slack）の3階層で `runs.jsonl` に1行追記する。

工程の結果は独立に持つ（取得の成功と、保存・月印・push・画面反映・Slack の成否を混ぜない）:
  success / partial / waiting / failed / unverified（確かめていない）/ skipped（正常スキップ）/ not_applicable

成功に数えるのは status=success だけ。dry-run の run・skipped・not_applicable・unverified・
exit 0・ファイルの存在・0バイトのログ・Slack 控えだけは成功の証拠にしない（TASK 4.10）。

保持（TASK 4.12 D8）: 詳細な run 記録は 180 日、月次の集約は 3 年、期間経過だけでは自動削除しない。
ここには削除処理を置かない（aged_candidates で候補を見るだけ）。実額・秘密は記録しない
（detail は短い事実文だけ。呼び出し側が金額を渡さない）。
"""
from __future__ import annotations

import fcntl
import json
import os
import secrets
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

JST = ZoneInfo("Asia/Tokyo")
REPO = Path(__file__).resolve().parents[1]

SYSTEMS = ("teiki", "etc", "vpoint", "card_benefit")
STAGES = ("fetch", "save", "save_verify", "stamp", "push", "display", "slack")
STATUSES = ("success", "partial", "waiting", "failed", "unverified", "skipped", "not_applicable")
SEVERITY = {"failed": 4, "unverified": 3, "partial": 2, "waiting": 1, "success": 0}
RETENTION_DETAIL_DAYS = 180
RETENTION_MONTHLY_DAYS = 365 * 3


def state_dir() -> Path:
    env = (os.environ.get("JARVIS_STATE_DIR") or "").strip()
    return Path(env).expanduser() if env else REPO / ".jarvis_state"


def log_dir() -> Path:
    env = (os.environ.get("JARVIS_614_LOG_DIR") or "").strip()
    return Path(env).expanduser() if env else state_dir() / "614_watch"


def runs_path() -> Path:
    return log_dir() / "runs.jsonl"


def now_iso() -> str:
    return datetime.now(JST).isoformat(timespec="seconds")


def new_run_id(system: str = "614") -> str:
    """run_id は JARVIS_614_RUN_ID があればそれ（親の run に子の呼び出しをひも付ける）。"""
    env = (os.environ.get("JARVIS_614_RUN_ID") or "").strip()
    if env:
        return env
    return f"{system}-{datetime.now(JST).strftime('%Y%m%dT%H%M%S')}-{secrets.token_hex(2)}"


def derive_outcome(stages: dict[str, dict[str, Any]]) -> str:
    """系統の結果＝実行した工程のうち一番悪いもの。何も実行していなければ skipped。"""
    ran = [s["status"] for s in stages.values() if s["status"] not in ("skipped", "not_applicable")]
    if not ran:
        return "skipped"
    return max(ran, key=lambda s: SEVERITY.get(s, 0))


class RunRecord:
    """1 run の記録。stage() で工程を足し、finish() で runs.jsonl に1行追記する（失敗しても本線を止めない）。"""

    def __init__(self, *, run_id: str | None = None, dry_run: bool = False, trigger: str = "auto", script: str = ""):
        self.run_id = run_id or new_run_id()
        self.dry_run = bool(dry_run)
        self.trigger = trigger  # auto（launchd・朝の取りこぼし）／manual（人の依頼）
        self.script = script
        self.started_at = now_iso()
        self.systems: dict[str, dict[str, Any]] = {}
        self.note = ""

    def stage(self, system: str, stage: str, status: str, detail: str = "", error_code: str | None = None) -> None:
        if status not in STATUSES:
            raise ValueError(f"unknown status {status}")
        sysrec = self.systems.setdefault(system, {"stages": {}})
        sysrec["stages"][stage] = {
            "status": status,
            "detail": (detail or "")[:200],
            "error_code": error_code,
            "at": now_iso(),
        }

    def to_dict(self) -> dict[str, Any]:
        systems = {}
        for name, rec in self.systems.items():
            systems[name] = {"outcome": derive_outcome(rec["stages"]), "stages": rec["stages"]}
        return {
            "run_id": self.run_id,
            "script": self.script,
            "trigger": self.trigger,
            "dry_run": self.dry_run,
            "started_at": self.started_at,
            "ended_at": now_iso(),
            "outcome": derive_outcome({n: {"status": s["outcome"]} for n, s in systems.items()}),
            "systems": systems,
            "note": self.note[:200],
        }

    def finish(self) -> dict[str, Any]:
        rec = self.to_dict()
        append_run(rec)
        return rec


def append_run(rec: dict[str, Any], path: Path | None = None) -> bool:
    """1行追記（排他・O_APPEND）。失敗しても例外を投げない（記録の失敗で本線を落とさない）。"""
    p = path or runs_path()
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(rec, ensure_ascii=False, separators=(",", ":")) + "\n"
        fd = os.open(p, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            os.write(fd, line.encode("utf-8"))
            os.fsync(fd)
        finally:
            os.close(fd)
        return True
    except OSError:
        return False


def read_runs(path: Path | None = None) -> list[dict[str, Any]]:
    p = path or runs_path()
    out: list[dict[str, Any]] = []
    try:
        for ln in p.read_text(encoding="utf-8").splitlines():
            try:
                d = json.loads(ln)
            except json.JSONDecodeError:
                continue  # 壊れた行は読み飛ばす（消さない）
            if isinstance(d, dict):
                out.append(d)
    except OSError:
        pass
    return out


def success_count(runs: list[dict[str, Any]], *, system: str | None = None, stage: str | None = None) -> int:
    """成功に数える run/系統/工程の数。dry-run・skipped・not_applicable・unverified・部分成功・失敗は数えない。"""
    n = 0
    for r in runs:
        if r.get("dry_run"):
            continue
        for name, srec in (r.get("systems") or {}).items():
            if system and name != system:
                continue
            if stage:
                if ((srec.get("stages") or {}).get(stage) or {}).get("status") == "success":
                    n += 1
            elif srec.get("outcome") == "success":
                n += 1
    return n


def stage_counts(runs: list[dict[str, Any]], *, system: str, stage: str) -> dict[str, int]:
    """工程ごとの結果別件数（dry-run は別枠 'dry_run' に分け、成功と混ぜない）。"""
    out: dict[str, int] = {}
    for r in runs:
        srec = (r.get("systems") or {}).get(system)
        if not srec:
            continue
        st = ((srec.get("stages") or {}).get(stage) or {}).get("status")
        if st is None:
            continue
        key = "dry_run" if r.get("dry_run") else st
        out[key] = out.get(key, 0) + 1
    return out


def aged_candidates(
    *, days: int = RETENTION_DETAIL_DAYS, now: datetime | None = None, path: Path | None = None
) -> list[str]:
    """保持期間を過ぎた run の run_id 一覧。削除はしない（期間経過だけでは自動削除しない・人が点検して決める）。"""
    cutoff = (now or datetime.now(JST)) - timedelta(days=days)
    ids = []
    for r in read_runs(path):
        try:
            if datetime.fromisoformat(str(r.get("started_at"))) < cutoff:
                ids.append(str(r.get("run_id")))
        except ValueError:
            continue
    return ids
