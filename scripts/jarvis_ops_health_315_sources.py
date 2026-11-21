"""315-A collection only: no live login, token writes, baseline writes or posting."""
from __future__ import annotations

import contextlib
import io
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
# Weekly cadence + six hours of scheduling / collection allowance.
MAX_AGE_HOURS = 174


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


def square_snapshot(path: Path | None = None) -> tuple[str, str]:
    try:
        state = json.loads((path or REPO / ".jarvis_state/square_probe.json").read_text())
        detail = state.get("last_probe")
        if not isinstance(detail, dict) or not recent(state.get("last_probe_at")):
            return "確認不能", "保存済みprobeなし／古い結果（上限174時間）"
        if not isinstance(detail.get("ok"), bool):
            return "確認不能", "保存済みprobeの判定なし"
        ok = detail["ok"] and not state.get("structural_limit", False)
        return ("OK" if ok else "異常"), "保存済みprobeのみ参照（live未実行）"
    except (OSError, ValueError, TypeError, AttributeError):
        return "確認不能", "保存済みprobeを読取できない"


def chrline_snapshot() -> tuple[str, str]:
    # Existing health API is read-only with save_baseline=False. Do not render
    # its per-folder block: it contains private names / paths.
    try:
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
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
            if current["decode_seen"] == 0:
                return "確認不能", "CHRLINE直近decode標本なし"
            alerts = evaluate_alerts(current, previous)
            return ("異常" if alerts else "OK"), f"CHRLINE health: 警告{len(alerts)}件（baseline保存なし）"
    except Exception:
        # Never put exception text (paths, token values) into report/log.
        return "確認不能", "CHRLINE healthを取得できない"


def collect(run, *, cloud: bool) -> dict[str, tuple[str, str]]:
    deferred = ("スキップ(cloud)", "Mac日曜21:45で補完")
    return {
        "315 GHA": gha_snapshot(run),
        "Square probe": deferred if cloud else square_snapshot(),
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
