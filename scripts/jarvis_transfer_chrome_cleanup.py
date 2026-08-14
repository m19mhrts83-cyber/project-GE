#!/usr/bin/env python3
"""送金アシスト用 Chrome（CDP profile）を閉じる。

振込レール完了・中断・セッション終了時に呼ぶ。日常 Chrome / Vpass は触らない。

  python scripts/jarvis_transfer_chrome_cleanup.py
  python scripts/jarvis_transfer_chrome_cleanup.py --dry-run
  python scripts/jarvis_transfer_chrome_cleanup.py --ports 9241,9242,9244
"""

from __future__ import annotations

import argparse
import os
import signal
import subprocess
import time
from pathlib import Path

# 送金アシスト専用 user-data-dir 名（~/.jarvis_state/ 配下）
TRANSFER_PROFILES = (
    "chrome_ib_shiga",
    "chrome_ib_mufg_chikage",
    "chrome_ib_kyoto",
    "chrome_sbi_net_transfer",
    "chrome_sbi_chuukai",
)

# 既定の送金 CDP ポート（launcher と揃える）
DEFAULT_PORTS = (9241, 9242, 9243, 9244)


def _pgrep_f(pattern: str) -> list[int]:
    try:
        out = subprocess.check_output(
            ["pgrep", "-f", pattern], text=True, stderr=subprocess.DEVNULL
        )
    except subprocess.CalledProcessError:
        return []
    pids: list[int] = []
    for line in out.splitlines():
        line = line.strip()
        if line.isdigit():
            pids.append(int(line))
    return pids


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


def collect_pids(ports: list[int]) -> dict[str, list[int]]:
    found: dict[str, list[int]] = {}
    home = Path.home()
    for name in TRANSFER_PROFILES:
        # Chrome は user-data-dir=.../chrome_ib_shiga 形式
        pat = f"user-data-dir=.*{name}"
        pids = _pgrep_f(pat)
        if not pids:
            pids = _pgrep_f(str(home / ".jarvis_state" / name))
        if pids:
            found[name] = sorted(set(pids))
    pw = _pgrep_f("playwright_chromiumdev_profile")
    if pw:
        found["playwright_tmp"] = sorted(set(pw))
    for port in ports:
        pids = _lsof_listen(port)
        if pids:
            found[f"port_{port}"] = sorted(set(pids))
    return found


def kill_pids(pids: set[int], *, force: bool = False) -> None:
    sig = signal.SIGKILL if force else signal.SIGTERM
    for pid in sorted(pids):
        try:
            os.kill(pid, sig)
        except ProcessLookupError:
            pass
        except PermissionError:
            print(f"  skip pid={pid} (permission)")


def main() -> int:
    p = argparse.ArgumentParser(description="Close transfer-assist Chrome CDP sessions")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument(
        "--ports",
        default=",".join(str(x) for x in DEFAULT_PORTS),
        help="comma-separated CDP ports",
    )
    p.add_argument("--force", action="store_true", help="SIGKILL if still listening")
    args = p.parse_args()
    ports = [int(x) for x in args.ports.split(",") if x.strip().isdigit()]

    found = collect_pids(ports)
    if not found:
        print("📎 transfer Chrome: 閉じる対象なし")
        return 0

    all_pids: set[int] = set()
    print("📎 transfer Chrome cleanup")
    for label, pids in sorted(found.items()):
        print(f"  {label}: {pids}")
        all_pids.update(pids)

    if args.dry_run:
        print("  (dry-run — 終了しません)")
        return 0

    kill_pids(all_pids, force=False)
    time.sleep(1.5)
    still = collect_pids(ports)
    if still and args.force:
        rem: set[int] = set()
        for pids in still.values():
            rem.update(pids)
        kill_pids(rem, force=True)
        time.sleep(0.8)
        still = collect_pids(ports)

    if still:
        print("  ⚠️ 残存:", {k: v for k, v in still.items()})
        return 1
    print("  ✅ 送金用 Chrome を閉じました")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
