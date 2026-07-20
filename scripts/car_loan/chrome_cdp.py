"""CDP Chrome 起動・接続（銀行共通）。"""
from __future__ import annotations

import socket
import subprocess
import time
from pathlib import Path

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
DEFAULT_CDP_PORT = 9223


def cdp_ready(port: int) -> bool:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(1)
            s.connect(("127.0.0.1", port))
        return True
    except OSError:
        return False


def start_cdp_chrome(
    port: int = DEFAULT_CDP_PORT,
    profile_dir: Path | None = None,
    start_url: str = "about:blank",
) -> None:
    if not Path(CHROME).exists():
        raise RuntimeError(f"Google Chrome が見つかりません: {CHROME}")
    profile = profile_dir or (Path.home() / ".jarvis_state" / "chrome_car_loan")
    profile.mkdir(parents=True, exist_ok=True)
    if cdp_ready(port):
        print(f"📎 既存の CDP Chrome を利用します (port {port})")
        return
    args = [
        CHROME,
        f"--remote-debugging-port={port}",
        f"--user-data-dir={profile}",
        "--no-first-run",
        "--no-default-browser-check",
        start_url,
    ]
    print(f"📎 CDP Chrome を起動します (port {port}, profile {profile})")
    subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    for _ in range(40):
        if cdp_ready(port):
            time.sleep(0.8)
            print(f"📎 CDP 準備完了: http://127.0.0.1:{port}")
            return
        time.sleep(0.5)
    raise RuntimeError(f"CDP Chrome が port {port} で起動しませんでした")


def open_in_chrome(url: str) -> None:
    if not Path(CHROME).exists():
        raise RuntimeError(f"Google Chrome が見つかりません: {CHROME}")
    subprocess.run(["open", "-a", "Google Chrome", url], check=True)
    print(f"📎 Chrome で開きました: {url}")
