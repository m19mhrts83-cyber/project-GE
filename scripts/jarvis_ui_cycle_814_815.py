#!/usr/bin/env python3
"""814/815 俯瞰UI更新サイクル — 投影鮮度確認＋任意 push＋Slack #ops（問題時のみ）。

使い方:
  cd ~/git-repos && set -a && source .env.jarvis_private && set +a
  ~/selenium_env/venv/bin/python scripts/jarvis_ui_cycle_814_815.py
  ~/selenium_env/venv/bin/python scripts/jarvis_ui_cycle_814_815.py --push --post
  ~/selenium_env/venv/bin/python scripts/jarvis_ui_cycle_814_815.py --agent 814 --post
  ~/selenium_env/venv/bin/python scripts/jarvis_ui_cycle_814_815.py --post --force-post  # OKでも投稿

入口: sync_meta / 既存 runner
確認: Slack は問題時のみ自動。UI破壊的変更は人
履歴: 各係 logs/（常時）＋ Slack #ops（要フォロー時のみ）
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

AGENT_LABEL = {
    "814": "814 ダッシュ更新",
    "815": "815 KURASHIFT更新",
    "both": "814/815 UI更新",
}


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


def evaluate(meta: dict, push_rc: int | None) -> tuple[str, str]:
    """Return (overall, reason). overall is OK or 要フォロー…"""
    dash = meta.get("last_dashboard_log") or {}
    mtime = dash.get("mtime") or "—"
    overall = "OK"
    reason = ""
    try:
        if mtime != "—":
            dt = datetime.fromisoformat(str(mtime))
            age_h = (datetime.now(tz=JST) - dt.astimezone(JST)).total_seconds() / 3600
            if age_h > 48:
                overall = "要フォロー（投影ログ48h超）"
                reason = f"最終 push ログが約{age_h:.0f}h前（{dash.get('name', '—')} @ {mtime}）"
    except Exception:
        pass
    if push_rc is not None and push_rc != 0:
        overall = "要フォロー（push失敗）"
        reason = f"今回 push exit={push_rc}"
    if overall == "OK" and not meta.get("last_dashboard_log"):
        overall = "要フォロー（投影ログなし）"
        reason = "Library/Logs/jarvis_dashboard に push_*.log が無い"
    return overall, reason


def build_message(agent: str, meta: dict, push_rc: int | None) -> str:
    """Full log text (always written to logs/)."""
    now = datetime.now(JST).strftime("%Y-%m-%d %H:%M")
    dash = meta.get("last_dashboard_log") or {}
    mtime = dash.get("mtime") or "—"
    overall, _ = evaluate(meta, push_rc)
    label = AGENT_LABEL.get(agent, "814/815 UI更新")

    lines = [
        f"【社員報告】{label} / 定周期",
        f"- 状態: Phase L サイクル（{now} JST）",
        f"- 判定: {overall}",
        f"- 最終 dashboard push ログ: {dash.get('name', '—')} @ {mtime}",
    ]
    if push_rc is not None:
        lines.append(f"- 今回 push: exit={push_rc}")
    lines.append("- 見てほしい点: Dash/KURASHIFT の鮮度。破壊的UI変更はしない")
    lines.append("- 次: launchd dashboard-push（12:30）。#ops は要フォロー時のみ")
    return "\n".join(lines)


def build_ops_alert(agent: str, meta: dict, push_rc: int | None) -> str | None:
    """Short #ops text when problem; None when OK (skip post)."""
    overall, reason = evaluate(meta, push_rc)
    if overall == "OK":
        return None
    now = datetime.now(JST).strftime("%Y-%m-%d %H:%M")
    label = AGENT_LABEL.get(agent, "814/815 UI更新")
    dash = meta.get("last_dashboard_log") or {}
    lines = [
        f"⚠️ 【要確認】{label}",
        f"- 判定: {overall}",
        f"- 理由: {reason or '—'}",
        f"- 時刻: {now} JST",
    ]
    if dash.get("name"):
        lines.append(f"- 最終ログ: {dash.get('name')} @ {dash.get('mtime', '—')}")
    lines.append("- 次: Dash/KURASHIFT鮮度を確認。破壊的UI変更はしない")
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
    ap.add_argument(
        "--post",
        action="store_true",
        help="Slack #ops に投稿（既定: 要フォロー時のみ）",
    )
    ap.add_argument(
        "--force-post",
        action="store_true",
        help="判定OKでも #ops に投稿（検証用）",
    )
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
    overall, _ = evaluate(meta, push_rc)
    msg = build_message(args.agent, meta, push_rc)
    alert = build_ops_alert(args.agent, meta, push_rc)
    print(msg)
    if overall == "OK":
        print("\n📎 #ops: 問題なし → 投稿スキップ（logs のみ）")
    else:
        print("\n📎 #ops 投稿予定:\n" + (alert or msg))

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

    to_post = msg if args.force_post and alert is None else alert
    if to_post is None:
        print("📎 Slack #ops: skipped (OK)")
        return 0 if push_rc in (None, 0) else push_rc
    return post_ops(to_post)


if __name__ == "__main__":
    raise SystemExit(main())
