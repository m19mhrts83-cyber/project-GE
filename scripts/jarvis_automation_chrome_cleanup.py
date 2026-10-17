#!/usr/bin/env python3
"""自動化用 Google Chrome（専用 user-data-dir）をまとめて閉じる。

日常の Chrome（デフォルトプロファイル）は触らない。
Dock に Chrome が複数残る主因は、これらのプロセスの放置。

  python scripts/jarvis_automation_chrome_cleanup.py
  python scripts/jarvis_automation_chrome_cleanup.py --dry-run
  python scripts/jarvis_automation_chrome_cleanup.py --force

対象:
  - ~/.jarvis_state/chrome_*
  - NotebookLM MCP / studio プロファイル
  - Playwright 一時プロファイル
  - 既知の自動化 CDP ポート上の Chrome
"""
from __future__ import annotations

import argparse
import os
import signal
import subprocess
import time
from pathlib import Path

STATE = Path.home() / ".jarvis_state"

# 名前が chrome_ 以外でも自動化用
EXTRA_PROFILE_DIRS = (
    Path.home() / "Library/Application Support/notebooklm-mcp/chrome_profile",
    Path.home() / "Library/Application Support/notebooklm-studio/chrome_profile",
)

# 送金・Vpass・テイチャン等で使う CDP ポート
DEFAULT_PORTS = (
    9223,
    9233,
    9235,
    9241,
    9242,
    9243,
    9244,
)


def _pgrep_f(pattern: str) -> list[int]:
    try:
        out = subprocess.check_output(
            ["pgrep", "-f", pattern], text=True, stderr=subprocess.DEVNULL
        )
    except subprocess.CalledProcessError:
        return []
    return [int(x) for x in out.splitlines() if x.strip().isdigit()]


def _lsof_listen(port: int) -> list[int]:
    try:
        out = subprocess.check_output(
            ["lsof", "-nP", f"-iTCP:{port}", "-sTCP:LISTEN", "-t"],
            text=True,
            stderr=subprocess.DEVNULL,
        )
    except subprocess.CalledProcessError:
        return []
    return [int(x) for x in out.split() if x.isdigit()]


def _is_google_chrome_automation(pid: int) -> bool:
    try:
        cmd = subprocess.check_output(
            ["ps", "-p", str(pid), "-o", "command="], text=True
        ).strip()
    except subprocess.CalledProcessError:
        return False
    if "/Applications/Google Chrome.app/" not in cmd:
        return False
    if "user-data-dir=" not in cmd:
        return False
    # 日常 Chrome（デフォルト Application Support/Google/Chrome）は除外
    if "Application Support/Google/Chrome" in cmd and ".jarvis_state" not in cmd:
        if "notebooklm" not in cmd and "playwright" not in cmd:
            return False
    return True


def collect() -> dict[str, list[int]]:
    found: dict[str, list[int]] = {}

    if STATE.is_dir():
        for p in sorted(STATE.glob("chrome_*")):
            if not p.is_dir():
                continue
            pids = [x for x in _pgrep_f(f"user-data-dir=.*{p.name}") if _is_google_chrome_automation(x)]
            if pids:
                found[p.name] = sorted(set(pids))

    for p in EXTRA_PROFILE_DIRS:
        if not p.exists():
            continue
        pids = [x for x in _pgrep_f(str(p)) if _is_google_chrome_automation(x)]
        if pids:
            found[p.name] = sorted(set(pids))

    pw = [x for x in _pgrep_f("playwright_chromiumdev_profile") if _is_google_chrome_automation(x)]
    if pw:
        found["playwright_tmp"] = sorted(set(pw))

    for port in DEFAULT_PORTS:
        pids = [x for x in _lsof_listen(port) if _is_google_chrome_automation(x)]
        if pids:
            found[f"port_{port}"] = sorted(set(pids))

    return found


def kill_pids(pids: set[int], *, force: bool) -> None:
    sig = signal.SIGKILL if force else signal.SIGTERM
    for pid in sorted(pids):
        try:
            os.kill(pid, sig)
        except ProcessLookupError:
            pass
        except PermissionError:
            print(f"  skip pid={pid} (permission)")


def main() -> int:
    ap = argparse.ArgumentParser(description="Close Jarvis automation Chrome sessions")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force", action="store_true", help="SIGKILL（既定も最終的に KILL）")
    args = ap.parse_args()

    found = collect()
    if not found:
        print("📎 自動化 Chrome: 閉じる対象なし")
        return 0

    all_pids: set[int] = set()
    print("📎 自動化 Chrome cleanup")
    for label, pids in sorted(found.items()):
        print(f"  {label}: {pids}")
        all_pids.update(pids)

    if args.dry_run:
        print("  (dry-run — 終了しません)")
        return 0

    kill_pids(all_pids, force=False)
    time.sleep(1.2)
    still = collect()
    if still:
        rem: set[int] = set()
        for pids in still.values():
            rem.update(pids)
        kill_pids(rem, force=True)
        time.sleep(0.6)
        still = collect()

    if still:
        print("  ⚠️ 残存:", {k: v for k, v in still.items()})
        return 1
    print("  ✅ 自動化用 Chrome を閉じました（日常 Chrome は未変更）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
