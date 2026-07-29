#!/usr/bin/env python3
"""
Jarvis: WeStudy 週次取込（GitHub Actions）の直近結果を確認し、定型ブロックを出力。

使い方:
  python scripts/jarvis_westudy_weekly_check.py
  python scripts/jarvis_westudy_weekly_check.py --mark-checked
  python scripts/jarvis_westudy_weekly_check.py --json

安定確認まで（連続成功 2 回）はパートナー確認・日曜セッション等で実行する。
state: ~/git-repos/.jarvis_state/westudy_weekly_watch.json
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

JST = ZoneInfo("Asia/Tokyo")
REPO = Path(__file__).resolve().parents[1]
STATE_PATH = REPO / ".jarvis_state" / "westudy_weekly_watch.json"
WORKFLOW = "westudy-raimo-weekly.yml"
SUCCESS_NEEDED = 2


def load_state() -> dict:
    if not STATE_PATH.is_file():
        return {
            "disabled": False,
            "consecutive_successes": 0,
            "last_checked_at": None,
            "last_run_id": None,
            "last_conclusion": None,
            "last_result_note": "",
        }
    try:
        data = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        data = {}
    if not isinstance(data, dict):
        data = {}
    data.setdefault("disabled", False)
    data.setdefault("consecutive_successes", 0)
    data.setdefault("last_checked_at", None)
    data.setdefault("last_run_id", None)
    data.setdefault("last_conclusion", None)
    data.setdefault("last_result_note", "")
    return data


def save_state(data: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def gh_run_list(limit: int = 3) -> list[dict]:
    cmd = [
        "gh",
        "run",
        "list",
        f"--workflow={WORKFLOW}",
        "--limit",
        str(limit),
        "--json",
        "databaseId,conclusion,status,displayTitle,createdAt,updatedAt,url,headBranch,event",
    ]
    try:
        out = subprocess.check_output(cmd, cwd=str(REPO), text=True, stderr=subprocess.STDOUT)
    except FileNotFoundError:
        raise RuntimeError("gh コマンドが見つかりません")
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"gh run list 失敗: {e.output.strip()[:400]}")
    rows = json.loads(out or "[]")
    return rows if isinstance(rows, list) else []


def fmt_jst(iso: str | None) -> str:
    if not iso:
        return "—"
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(JST)
        return dt.strftime("%Y-%m-%d %H:%M JST")
    except ValueError:
        return iso


def build_block(state: dict, runs: list[dict], *, force: bool) -> tuple[str, dict]:
    if state.get("disabled") and not force:
        return "", state

    if not runs:
        note = "実行履歴なし（workflow 未実行または gh 権限不足）"
        lines = [
            "📎 WeStudy週次",
            f"- 状態: 不明（{note}）",
            f"- 連続成功: {state.get('consecutive_successes', 0)}/{SUCCESS_NEEDED}",
            "- 確認: `gh run list --workflow=westudy-raimo-weekly.yml --limit 3`",
        ]
        return "\n".join(lines), state

    latest = runs[0]
    conclusion = (latest.get("conclusion") or "").strip() or None
    status = (latest.get("status") or "").strip()
    run_id = latest.get("databaseId")
    url = latest.get("url") or ""
    when = fmt_jst(latest.get("updatedAt") or latest.get("createdAt"))

    if status and status != "completed":
        label = f"実行中（{status}）"
        ok = None
    elif conclusion == "success":
        label = "成功"
        ok = True
    elif conclusion in ("failure", "timed_out", "cancelled"):
        label = f"失敗（{conclusion}）"
        ok = False
    else:
        label = f"完了（{conclusion or 'unknown'}）"
        ok = False

    lines = [
        "📎 WeStudy週次",
        f"- 最新: {label} @ {when}",
        f"- run: {run_id}" + (f" — {url}" if url else ""),
    ]
    if ok is False:
        lines.append(
            "- 対処: `gh run view %s --log-failed` → 必要なら "
            "`gh workflow run westudy-raimo-weekly.yml -f force_scrape=true`"
            % run_id
        )
    consec = int(state.get("consecutive_successes") or 0)
    if ok is True and str(run_id) != str(state.get("last_run_id") or ""):
        # 新しい成功 run のみカウント（同一 run の再確認では増やさない）
        pass  # counting happens in --mark-checked
    lines.append(f"- 連続成功（記録）: {consec}/{SUCCESS_NEEDED}" + (" · watch中" if not state.get("disabled") else ""))
    if consec >= SUCCESS_NEEDED and not state.get("disabled"):
        lines.append("- ヒント: 連続成功に達したら `--mark-stable` または state で disabled 可")

    note = f"{label}; run={run_id}"
    return "\n".join(lines), {
        **state,
        "last_conclusion": conclusion or status,
        "last_run_id": run_id,
        "last_result_note": note,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="WeStudy 週次 CI 結果チェック")
    ap.add_argument("--json", action="store_true", help="JSON 出力")
    ap.add_argument("--force", action="store_true", help="disabled でも出力")
    ap.add_argument(
        "--mark-checked",
        action="store_true",
        help="確認時刻を記録。成功なら連続成功を更新（同一 run_id は重複カウントしない）",
    )
    ap.add_argument(
        "--mark-stable",
        action="store_true",
        help="watch を終了（disabled=true）",
    )
    ap.add_argument("--limit", type=int, default=3)
    args = ap.parse_args()

    if os.environ.get("JARVIS_WESTUDY_WEEKLY_WATCH_DISABLE") == "1":
        if not args.force:
            return 0

    state = load_state()
    if args.mark_stable:
        state["disabled"] = True
        state["last_checked_at"] = datetime.now(JST).isoformat(timespec="seconds")
        save_state(state)
        print("📎 WeStudy週次: watch を disabled にしました")
        return 0

    if state.get("disabled") and not args.force:
        return 0

    try:
        runs = gh_run_list(limit=max(1, args.limit))
    except RuntimeError as e:
        print(f"📎 WeStudy週次\n- 状態: 確認失敗（{e}）", file=sys.stderr)
        return 1

    block, preview = build_block(state, runs, force=args.force)

    if args.mark_checked and runs:
        latest = runs[0]
        conclusion = (latest.get("conclusion") or "").strip()
        run_id = latest.get("databaseId")
        prev_id = state.get("last_run_id")
        consec = int(state.get("consecutive_successes") or 0)
        if conclusion == "success":
            if str(run_id) != str(prev_id or ""):
                consec += 1
        elif conclusion in ("failure", "timed_out", "cancelled"):
            if str(run_id) != str(prev_id or ""):
                consec = 0
        state["consecutive_successes"] = consec
        state["last_run_id"] = run_id
        state["last_conclusion"] = conclusion or latest.get("status")
        state["last_checked_at"] = datetime.now(JST).isoformat(timespec="seconds")
        state["last_result_note"] = preview.get("last_result_note") or ""
        if consec >= SUCCESS_NEEDED:
            # 自動解除はしない（ユーザー合意）。記録のみ
            pass
        save_state(state)
        block, _ = build_block(state, runs, force=True)

    if args.json:
        print(
            json.dumps(
                {"state": load_state() if args.mark_checked else state, "runs": runs, "block": block},
                ensure_ascii=False,
                indent=2,
            )
        )
    elif block:
        print(block)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
