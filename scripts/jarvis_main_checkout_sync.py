#!/usr/bin/env python3
"""Mac の main checkout を origin/main に追従させる（fast-forward のみ）。

launchd の定期処理は ~/git-repos（main checkout）のコードで動く。
PR を main にマージしても、この checkout が古いままだと直した修正が効かない
（2026-10-25〜26: FB 定型文・111 連投・211 クローズ案件の除外が丸1日効かなかった）。

- 遅れていて、手元だけのコミットが無い → `git merge --ff-only origin/main`
- 手元だけのコミットがある／ff できない → 自動では触らず #ops に1日1回知らせる
- main 以外を checkout 中・merge/rebase 途中 → 何もしない

  python scripts/jarvis_main_checkout_sync.py --dry-run
  python scripts/jarvis_main_checkout_sync.py --apply

停止: JARVIS_MAIN_CHECKOUT_SYNC_DISABLE=1
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

REPO = Path(__file__).resolve().parents[1]
STATE = REPO / ".jarvis_state" / "main_checkout_sync.json"
POST = REPO / "scripts" / "jarvis_slack_webhook_post.py"
JST = ZoneInfo("Asia/Tokyo")


def _git(*args: str) -> tuple[int, str]:
    r = subprocess.run(
        ["git", *args], cwd=str(REPO), capture_output=True, text=True, check=False
    )
    return r.returncode, (r.stdout + r.stderr).strip()


def _count(rng: str) -> int:
    code, out = _git("rev-list", "--count", rng)
    return int(out) if code == 0 and out.isdigit() else 0


def _load() -> dict:
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _save(d: dict) -> None:
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(d, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def build_alert(*, behind: int, ahead: int, reason: str) -> str:
    lines = [
        "【ops】Mac の作業フォルダが古いまま",
        f"main より {behind}件遅れ（手元だけのコミット {ahead}件）",
        "マージ済みの修正が Mac の定期処理に効いていません",
        "",
        f"理由: {reason}",
        "次: Mac で `git pull --rebase origin main`（Jarvis に一声でも可）",
    ]
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true", help="ff を実行し、必要なら #ops へ")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    dry = args.dry_run or not args.apply

    if (os.environ.get("JARVIS_MAIN_CHECKOUT_SYNC_DISABLE") or "").strip() in ("1", "true", "yes"):
        print("⏭ disabled")
        return 0
    if (REPO / ".git").is_file():
        print("⏭ worktree のため対象外（main checkout だけ追従）")
        return 0
    code, branch = _git("rev-parse", "--abbrev-ref", "HEAD")
    if code != 0 or branch != "main":
        print(f"⏭ main 以外を checkout 中（{branch}）")
        return 0
    for marker in ("MERGE_HEAD", "rebase-merge", "rebase-apply", "CHERRY_PICK_HEAD"):
        if (REPO / ".git" / marker).exists():
            print(f"⏭ {marker} 進行中")
            return 0

    code, out = _git("fetch", "-q", "origin", "main")
    if code != 0:
        print(f"⚠️ fetch failed: {out}", file=sys.stderr)
        return 1
    behind = _count("HEAD..origin/main")
    ahead = _count("origin/main..HEAD")
    print(f"📎 main: behind={behind} ahead={ahead}")
    state = _load()
    today = datetime.now(JST).strftime("%Y-%m-%d")
    if behind == 0:
        state.update({"last_ok_at": datetime.now(JST).isoformat(timespec="seconds")})
        if not dry:
            _save(state)
        return 0

    reason = ""
    if ahead == 0:
        if dry:
            print("# dry-run: would git merge --ff-only origin/main")
            return 0
        code, out = _git("merge", "--ff-only", "-q", "origin/main")
        if code == 0:
            print(f"✅ fast-forward {behind}件")
            state.update(
                {
                    "last_ok_at": datetime.now(JST).isoformat(timespec="seconds"),
                    "last_ff": behind,
                }
            )
            _save(state)
            return 0
        reason = "手元の未コミット変更と同じファイルが更新されている"
        print(f"⚠️ ff failed: {out[:300]}", file=sys.stderr)
    else:
        reason = "手元だけのコミットがあり自動では追従しない"

    if state.get("last_alert_date") == today:
        print("⏭ 本日通知済み")
        return 0
    text = build_alert(behind=behind, ahead=ahead, reason=reason)
    if dry:
        print("--- dry-run #ops ---\n" + text)
        return 0
    r = subprocess.run(
        [sys.executable, str(POST), "--channel", "ops", "--text", text],
        cwd=str(REPO),
        check=False,
    )
    if r.returncode == 0:
        state["last_alert_date"] = today
        _save(state)
    return int(r.returncode)


if __name__ == "__main__":
    raise SystemExit(main())
