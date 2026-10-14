#!/usr/bin/env python3
"""814/815 俯瞰UI更新サイクル — 投影鮮度確認＋任意 push＋Slack #ops。

使い方:
  cd ~/git-repos && set -a && source .env.jarvis_private && set +a
  ~/selenium_env/venv/bin/python scripts/jarvis_ui_cycle_814_815.py
  ~/selenium_env/venv/bin/python scripts/jarvis_ui_cycle_814_815.py --push --post
  ~/selenium_env/venv/bin/python scripts/jarvis_ui_cycle_814_815.py --agent 814 --post

入口: sync_meta / 既存 runner
確認: Slack は自動可。UI破壊的変更は人
履歴: 各係 logs/ ＋ Slack #ops
停止: JARVIS_UI_CYCLE_DISABLE=1
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
PY = Path("/Users/matsunomasaharu2/selenium_env/venv/bin/python")
LOG814 = (
    REPO
    / "docs/AIエージェントチーム/800_俯瞰UI・投影更新室/814_Jarvisダッシュボード更新係/logs"
)
LOG815 = (
    REPO
    / "docs/AIエージェントチーム/800_俯瞰UI・投影更新室/815_KURASHIFT更新係/logs"
)


def _run(cmd: list[str], *, timeout: int = 300) -> tuple[int, str]:
    try:
        p = subprocess.run(
            cmd,
            cwd=str(REPO),
            capture_output=True,
            text=True,
            timeout=timeout,
            env=os.environ.copy(),
        )
    except (OSError, subprocess.TimeoutExpired) as e:
        return 1, str(e)
    return p.returncode, ((p.stdout or "") + ("\n" + p.stderr if p.stderr else "")).strip()


def fetch_sync_meta() -> dict:
    """Best-effort: read sync_meta via dashboard push helper / supabase if available."""
    out: dict = {}
    # Prefer existing state files
    for name in (
        "dashboard_push_last.json",
        "situation_watch_last.json",
        "kurashift_gmail_read_reminder.json",
    ):
        p = REPO / ".jarvis_state" / name
        if p.is_file():
            try:
                out[name] = json.loads(p.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                out[name] = {"error": "read_fail"}
    # Log dir freshness
    log_dir = Path.home() / "Library/Logs/jarvis_dashboard"
    if log_dir.is_dir():
        logs = sorted(log_dir.glob("push_*.log"), key=lambda x: x.stat().st_mtime, reverse=True)
        if logs:
            out["last_dashboard_log"] = {
                "name": logs[0].name,
                "mtime": datetime.fromtimestamp(logs[0].stat().st_mtime, tz=JST).isoformat(
                    timespec="seconds"
                ),
            }
    return out


def build_message(agent: str, meta: dict, push_rc: int | None) -> str:
    now = datetime.now(JST).strftime("%Y-%m-%d %H:%M")
    dash = meta.get("last_dashboard_log") or {}
    mtime = dash.get("mtime") or "—"
    overall = "OK"
    # stale if no log in 2 days
    try:
        if mtime != "—":
            dt = datetime.fromisoformat(str(mtime))
            age_h = (datetime.now(tz=JST) - dt.astimezone(JST)).total_seconds() / 3600
            if age_h > 48:
                overall = "要フォロー（投影ログ48h超）"
    except Exception:
        pass
    if push_rc is not None and push_rc != 0:
        overall = "要フォロー（push失敗）"

    lines = [
        f"【社員報告】{'814 ダッシュ更新' if agent == '814' else '815 KURASHIFT更新' if agent == '815' else '814/815 UI更新'} / 定周期",
        f"- 状態: Phase L サイクル（{now} JST）",
        f"- 判定: {overall}",
        f"- 最終 dashboard push ログ: {dash.get('name', '—')} @ {mtime}",
    ]
    if push_rc is not None:
        lines.append(f"- 今回 push: exit={push_rc}")
    lines.append("- 見てほしい点: Dash/KURASHIFT の鮮度。破壊的UI変更はしない")
    lines.append("- 次: launchd dashboard-push（12:30）＋本コマンド --post。将来は816アプリ")
    lines.append(
        "- フロー814: https://flowforge-259747770348.asia-northeast1.run.app/flows/flow_wkFbA0v6bq3ouq9dmpX-cxc1"
    )
    lines.append(
        "- フロー815: https://flowforge-259747770348.asia-northeast1.run.app/flows/flow_Xy85GrVwta9qwVlLQcHAwNjI"
    )
    return "\n".join(lines)


def post_ops(text: str) -> int:
    py = str(PY if PY.is_file() else sys.executable)
    code, out = _run(
        [
            py,
            str(REPO / "scripts" / "jarvis_slack_webhook_post.py"),
            "--channel",
            "ops",
            "--username",
            "814/815 UI更新",
            "--text",
            text,
        ],
        timeout=60,
    )
    print(out)
    return code


def main() -> int:
    if os.environ.get("JARVIS_UI_CYCLE_DISABLE") == "1":
        print("📎 UI cycle: disabled")
        return 0

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--agent", choices=("814", "815", "both"), default="both")
    ap.add_argument("--push", action="store_true", help="jarvis_dashboard_push.py を実行")
    ap.add_argument("--post", action="store_true", help="Slack #ops に投稿")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    push_rc: int | None = None
    if args.push:
        py = str(PY if PY.is_file() else sys.executable)
        # soft situation_watch then push
        _run([py, str(REPO / "scripts" / "jarvis_situation_watch.py")], timeout=180)
        push_rc, out = _run(
            [py, str(REPO / "scripts" / "jarvis_dashboard_push.py")],
            timeout=300,
        )
        if out:
            print(out[-2000:])

    meta = fetch_sync_meta()
    msg = build_message(args.agent, meta, push_rc)
    print(msg)

    stamp = datetime.now(JST).strftime("%Y%m%d_%H%M%S")
    for log_dir, who in ((LOG814, "814"), (LOG815, "815")):
        if args.agent not in ("both", who):
            continue
        log_dir.mkdir(parents=True, exist_ok=True)
        (log_dir / f"{stamp}_ui_cycle.md").write_text(msg + "\n", encoding="utf-8")

    if args.dry_run or not args.post:
        if not args.post:
            print("\n（--post なし → Slack未投稿）")
        return 0 if push_rc in (None, 0) else push_rc
    return post_ops(msg)


if __name__ == "__main__":
    raise SystemExit(main())
