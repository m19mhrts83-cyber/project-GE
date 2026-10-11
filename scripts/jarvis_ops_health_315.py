#!/usr/bin/env python3
"""315 連携健全性点検係 — WeStudy/GHA ＋ オプチャ健全性をまとめ Slack #ops へ。

使い方:
  cd ~/git-repos && set -a && source .env.jarvis_private && set +a
  ~/selenium_env/venv/bin/python scripts/jarvis_ops_health_315.py
  ~/selenium_env/venv/bin/python scripts/jarvis_ops_health_315.py --post
  ~/selenium_env/venv/bin/python scripts/jarvis_ops_health_315.py --post --mark-checked

秘密は .env.jarvis_private（SLACK_WEBHOOK_AI_TEAM_OPS）。フォルダに URL を書かない。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

JST = ZoneInfo("Asia/Tokyo")
REPO = Path(__file__).resolve().parents[1]
PYTHON_MAC = Path("/Users/matsunomasaharu2/selenium_env/venv/bin/python")
LOG_DIR = (
    REPO
    / "docs"
    / "AIエージェントチーム"
    / "300_品質・タスク運用管理室"
    / "315_連携健全性点検係"
    / "logs"
)
WATCH_STATUS = (
    REPO / "line_unofficial_poc" / ".line_auth" / ".chrline_open_chat_watch_status.json"
)
OPENCHAT_BASE = Path(
    "~/Library/CloudStorage/OneDrive-個人用/215_神・大家さん倶楽部"
    "/C2_ルーティン作業/26_パートナー社への相談/815_神大家オプチャ"
).expanduser()
WATCH_ERR = Path.home() / "Library/Logs/line_open_chat/watch.err.log"
FLOW_URL = (
    "https://flowforge-259747770348.asia-northeast1.run.app"
    "/flows/flow_zYjp6A4HDURefJhSm0h_zUtX"
)


def _run(cmd: list[str], *, timeout: int = 120) -> tuple[int, str]:
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
    out = ((p.stdout or "") + ("\n" + p.stderr if p.stderr else "")).strip()
    return p.returncode, out


def _python() -> str:
    if PYTHON_MAC.is_file():
        return str(PYTHON_MAC)
    return sys.executable


def westudy_block(*, mark_checked: bool) -> tuple[str, str]:
    """Return (summary_line, full_block)."""
    py = _python()
    cmd = [py, str(REPO / "scripts" / "jarvis_westudy_weekly_check.py"), "--force"]
    if mark_checked:
        cmd.append("--mark-checked")
    code, out = _run(cmd, timeout=90)
    block = out.strip() or "📎 WeStudy週次\n- 状態: 出力なし"
    # 1行要約
    line = "確認失敗" if code != 0 else "OK"
    for m in re.finditer(r"^- .+$", block, re.M):
        s = m.group(0).lstrip("- ").strip()
        if "success" in s.lower() or "失敗" in s or "Fail" in s or "状態" in s:
            line = s[:120]
            break
    if "failure" in block.lower() or "Fail" in block:
        line = "⚠️ Fail疑い — 詳細はブロック参照"
    return line, block


def openchat_snapshot(*, cloud: bool = False) -> tuple[str, list[str]]:
    """Light health: watch status + today's 【スレッド】 counts. No QR / no YAML writes.

    cloud=True（GHA）: Mac専用（launchd / OneDrive / watchログ）はスキップし、
    判定を「要フォロー」にしない（本線は WeStudy/GHA）。
    """
    lines: list[str] = []
    level = "OK"

    if cloud:
        lines.append("実行環境: GitHub Actions（--cloud）")
        lines.append("オプチャ詳細: スキップ（Mac専用・launchd/OneDrive）")
        lines.append("補完: パートナー確認ついで／手動でフル点検可")
        return "スキップ(cloud)", lines

    # launchd
    uid = os.getuid()
    code, out = _run(
        ["launchctl", "print", f"gui/{uid}/com.matsunoma.line.openchat.watch"],
        timeout=15,
    )
    state_m = re.search(r"state = (\w+)", out or "")
    pid_m = re.search(r"pid = (\d+)", out or "")
    if code == 0 and state_m:
        st = state_m.group(1)
        pid = pid_m.group(1) if pid_m else "?"
        lines.append(f"launchd: {st} (pid={pid})")
        if st != "running":
            level = "要フォロー"
    else:
        lines.append("launchd: 取得失敗（未インストールの可能性）")
        level = "要フォロー"

    # watch status JSON
    hb = "—"
    if WATCH_STATUS.is_file():
        try:
            data = json.loads(WATCH_STATUS.read_text(encoding="utf-8"))
            hb = str(
                data.get("last_heartbeat")
                or data.get("heartbeat_at")
                or data.get("updated_at")
                or "—"
            )[:40]
            lines.append(f"watch heartbeat: {hb}")
        except (OSError, json.JSONDecodeError):
            lines.append("watch status: 読取失敗")
            level = "要フォロー"
    else:
        lines.append("watch status: ファイルなし")
        level = "要フォロー"

    # today's thread headings
    today = datetime.now(JST).strftime("%Y/%m/%d")
    total = 0
    if OPENCHAT_BASE.is_dir():
        for md in OPENCHAT_BASE.glob("*/5.やり取り.md"):
            try:
                text = md.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            n = len(re.findall(rf"### {re.escape(today)}.*【スレッド】", text))
            if n:
                total += n
        lines.append(f"今日の【スレッド】見出し: {total}件")
    else:
        lines.append("815フォルダ: 未マウント")
        level = "要フォロー"

    # recent exceptions
    if WATCH_ERR.is_file():
        code, err_out = _run(
            ["tail", "-n", "30", str(WATCH_ERR)],
            timeout=10,
        )
        hits = [
            ln
            for ln in (err_out or "").splitlines()
            if re.search(r"TypeError|Exception in thread|LOGGED_OUT|PermissionError", ln)
        ]
        if hits:
            lines.append(f"直近例外: あり（{hits[-1][:80]}）")
            level = "要フォロー"
        else:
            lines.append("直近例外: なし（tail30）")
    else:
        lines.append("watch.err.log: なし")

    return level, lines


def build_message(
    westudy_line: str,
    westudy_block: str,
    oc_level: str,
    oc_lines: list[str],
    *,
    cloud: bool = False,
) -> str:
    now = datetime.now(JST).strftime("%Y-%m-%d %H:%M")
    overall = "OK"
    if "⚠️" in westudy_line or "Fail" in westudy_line or "失敗" in westudy_line:
        overall = "要フォロー"
    if oc_level not in ("OK", "スキップ(cloud)"):
        overall = "要フォロー"

    engine = "GHA ops-health-315（日曜21:00 JST）" if cloud else "Mac手動／launchd補完"
    body = [
        f"【社員報告】連携健全性点検係（315） / 点検1回",
        f"- 時刻: {now} JST",
        f"- 起動: {engine}",
        f"- 判定: {overall}",
        f"- 報告先: Slack #ops（要判断のみ #consult。#report には出さない）",
        f"- フロー: {FLOW_URL}",
        f"- WeStudy/GHA: {westudy_line}",
        f"- オプチャ: {oc_level}",
    ]
    for ln in oc_lines:
        body.append(f"  · {ln}")
    if overall == "要フォロー":
        body.append("- 見てほしい点: 要フォロー。QR/YAML大量は人が確かめる → 必要なら #consult")
    else:
        body.append("- 見てほしい点: なし（OK）。異常時のみ対応")
    # keep Slack message readable; full westudy block in log
    if westudy_block and len(westudy_block) < 900:
        body.append("")
        body.append(westudy_block)
    return "\n".join(body)


def post_ops(text: str) -> int:
    py = _python()
    code, out = _run(
        [
            py,
            str(REPO / "scripts" / "jarvis_slack_webhook_post.py"),
            "--channel",
            "ops",
            "--username",
            "315 連携健全性点検係",
            "--text",
            text,
        ],
        timeout=60,
    )
    print(out)
    return code


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--post", action="store_true", help="Slack #ops に投稿")
    ap.add_argument(
        "--mark-checked",
        action="store_true",
        help="WeStudy watch の --mark-checked を付ける",
    )
    ap.add_argument(
        "--cloud",
        action="store_true",
        help="GHA用。オプチャのMac専用点検をスキップ",
    )
    ap.add_argument("--dry-run", action="store_true", help="投稿せず本文のみ表示")
    args = ap.parse_args()

    w_line, w_block = westudy_block(mark_checked=args.mark_checked)
    oc_level, oc_lines = openchat_snapshot(cloud=args.cloud)
    msg = build_message(w_line, w_block, oc_level, oc_lines, cloud=args.cloud)

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(JST).strftime("%Y%m%d_%H%M%S")
    log_path = LOG_DIR / f"{stamp}_ops_health.md"
    log_path.write_text(msg + "\n", encoding="utf-8")
    print(msg)
    print(f"\n📎 log: {log_path}")

    if args.dry_run or not args.post:
        if not args.post:
            print("\n（--post なし → Slack未投稿。投稿するときは --post）")
        return 0
    return post_ops(msg)


if __name__ == "__main__":
    raise SystemExit(main())
