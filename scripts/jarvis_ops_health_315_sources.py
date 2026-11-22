"""315-A collection only: no live login, token writes, baseline writes or posting."""
from __future__ import annotations

import contextlib
import io
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
# Weekly cadence + six hours of scheduling / collection allowance.
MAX_AGE_HOURS = 174
CHRLINE_PYTHON = REPO / "line_unofficial_poc" / ".venv" / "bin" / "python"
CHRLINE_TIMEOUT = 90
# Resident watch (com.matsunoma.line.openchat.watch) rewrites heartbeat_at about
# every minute, so 24h tolerates sleep/restart without waiting a week.
WATCH_MAX_AGE_HOURS = 24
SYNC_MAX_AGE_HOURS = 48
SYNC_MARKERS = (".chrline_sync_retry_queue.json", ".chrline_line_health_last.json")
WATCH_STATUS = REPO / "line_unofficial_poc" / ".line_auth" / ".chrline_open_chat_watch_status.json"


def recent(value: str, now: datetime | None = None) -> bool:
    try:
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
        age = ((now or datetime.now(timezone.utc)) - stamp).total_seconds() / 3600
        return 0 <= age <= MAX_AGE_HOURS
    except (ValueError, TypeError, AttributeError):
        return False


def gha_snapshot(run) -> tuple[str, str]:
    code, out = run([
        "gh", "run", "list", "--repo", "m19mhrts83-cyber/project-GE",
        "--workflow", "ops-health-315.yml", "--branch", "main", "--status", "completed",
        "--limit", "1", "--json", "conclusion,updatedAt",
    ], timeout=90)
    try:
        rows = json.loads(out) if code == 0 else []
        row = rows[0]
        if not recent(row.get("updatedAt")):
            return "確認不能", "315完了履歴が古い／日時不明"
        conclusion = row.get("conclusion")
        if conclusion not in ("success", "failure", "cancelled", "timed_out", "action_required", "startup_failure", "stale", "neutral", "skipped"):
            return "確認不能", "315完了履歴の結果不明"
        return ("OK" if conclusion == "success" else "異常"), f"315前回完了: {conclusion}"
    except (ValueError, TypeError, KeyError, IndexError, AttributeError):
        return "確認不能", "315完了履歴を取得できない"


def square_snapshot(path: Path | None = None, now: datetime | None = None) -> tuple[str, str]:
    """Square sync health from the resident open-chat watch's own status file.

    Read-only. Judges liveness (state + heartbeat age) and the latest write
    error. last_append_at is shown for reference only: no new posts is normal.
    The old manual probe (.jarvis_state/square_probe.json) is not consulted.
    """
    try:
        state = json.loads((path or WATCH_STATUS).read_text(encoding="utf-8"))
        if not isinstance(state, dict):
            return "確認不能", "常駐の状態ファイルが不正"
    except FileNotFoundError:
        return "確認不能", "常駐の状態ファイルなし"
    except (OSError, ValueError):
        return "確認不能", "常駐の状態ファイルを読取できない"
    beat = state.get("heartbeat_at") or state.get("updated_at")
    try:
        stamp = datetime.fromisoformat(str(beat))
        if stamp.tzinfo is None:
            return "確認不能", "常駐の最終確認時刻が不正"
        age = ((now or datetime.now(timezone.utc)) - stamp).total_seconds() / 3600
    except (ValueError, TypeError):
        return "確認不能", "常駐の最終確認時刻なし／不正"
    if not 0 <= age <= WATCH_MAX_AGE_HOURS:
        return "確認不能", f"常駐の最終確認が古い／未来（上限{WATCH_MAX_AGE_HOURS}時間）"
    if state.get("state") != "running":
        return "異常", f"常駐が稼働中でない（state={str(state.get('state'))[:20]}）"
    if state.get("last_write_error"):
        return "異常", "常駐に書込エラーの記録あり"
    appended = str(state.get("last_append_at") or "—")[:25]
    return "OK", f"常駐稼働中・最終確認{int(age)}時間前（最終追記 {appended}）"


def sync_age_hours(auth_dir: Path, now: float | None = None) -> float | None:
    """sync最終成功の目安（キュー/healthの最新更新時刻）からの経過時間。無ければNone。"""
    import time
    times = []
    for name in SYNC_MARKERS:
        try:
            times.append((auth_dir / name).stat().st_mtime)
        except OSError:
            pass
    if not times:
        return None
    return ((now if now is not None else time.time()) - max(times)) / 3600.0


def chrline_child() -> tuple[str, str]:
    """Runs inside the CHRLINE venv (needs CHRLINE/gevent). Read-only health."""
    # Existing health API is read-only with save_baseline=False. Do not render
    # its per-folder block: it contains private names / paths.
    try:
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            sys.path.insert(0, str(REPO / "line_unofficial_poc" / "chrline-patchv2"))
            sys.path.insert(0, str(REPO / "line_unofficial_poc"))
            from chrline_line_health import (
                build_health_snapshot, evaluate_alerts, load_previous_health,
                run_line_health_routine,
            )
            previous = load_previous_health()
            inv, _ = run_line_health_routine(save_baseline=False)
            if not inv.get("md_reports") or not all(r.get("exists") for r in inv["md_reports"]):
                return "確認不能", "CHRLINE入力資料が不足"
            current = build_health_snapshot(inv)
            note = ""
            if current["decode_seen"] == 0:
                age = sync_age_hours(REPO / "line_unofficial_poc" / ".line_auth")
                if age is None or age > SYNC_MAX_AGE_HOURS:
                    return "確認不能", "CHRLINE直近decode標本なし（syncも古い/不明）"
                note = f"・新着なし（sync最終成功{int(age)}時間前）"
            alerts = evaluate_alerts(current, previous)
            return ("異常" if alerts else "OK"), f"CHRLINE health: 警告{len(alerts)}件（baseline保存なし）{note}"
    except ModuleNotFoundError:
        return "確認不能", "CHRLINE healthを取得できない（モジュール不足）"
    except Exception:
        # Never put exception text (paths, token values) into report/log.
        return "確認不能", "CHRLINE healthを取得できない（読取エラー）"


_CHILD_CODE = (
    "import json,sys;sys.path.insert(0,sys.argv[1]);"
    "from jarvis_ops_health_315_sources import chrline_child;"
    "print('@@'+json.dumps(chrline_child(),ensure_ascii=False))"
)


def chrline_snapshot(python: Path | None = None, timeout: int = CHRLINE_TIMEOUT) -> tuple[str, str]:
    """Read CHRLINE health via the CHRLINE venv in a child process (read-only)."""
    py = python or CHRLINE_PYTHON
    if not Path(py).is_file():
        return "確認不能", "CHRLINE healthを取得できない（CHRLINE用venvなし）"
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(
        [str(REPO / "line_unofficial_poc" / "chrline-patchv2"), str(REPO / "line_unofficial_poc")]
    )
    try:
        proc = subprocess.run(
            [str(py), "-c", _CHILD_CODE, str(Path(__file__).resolve().parent)],
            capture_output=True, text=True, timeout=timeout, env=env, cwd=str(REPO),
        )
    except subprocess.TimeoutExpired:
        return "確認不能", f"CHRLINE healthを取得できない（タイムアウト{timeout}秒）"
    except OSError:
        return "確認不能", "CHRLINE healthを取得できない（起動失敗）"
    # Only our marked line is trusted; child stderr/other stdout may hold paths.
    for line in reversed(proc.stdout.splitlines()):
        if line.startswith("@@"):
            try:
                level, detail = json.loads(line[2:])
                return str(level), str(detail)
            except (ValueError, TypeError):
                break
    return "確認不能", f"CHRLINE healthを取得できない（子プロセス失敗 code={proc.returncode}）"


def collect(run, *, cloud: bool) -> dict[str, tuple[str, str]]:
    deferred = ("スキップ(cloud)", "Mac日曜21:45で補完")
    return {
        "315 GHA": gha_snapshot(run),
        "Square（オプチャ常駐）": deferred if cloud else square_snapshot(),
        "CHRLINE health": deferred if cloud else chrline_snapshot(),
    }


def collection_result(levels: list[str]) -> str:
    """Collection completeness, separate from health (OK / 要フォロー)."""
    measured = [x for x in levels if not x.startswith("スキップ")]
    unknown = sum(x == "確認不能" for x in measured)
    if not measured or unknown == len(measured):
        return "失敗"
    if unknown or len(measured) != len(levels):
        return "部分成功"
    return "成功"
