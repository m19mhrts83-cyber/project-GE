"""CDP Chrome 起動・接続（銀行・自動化共通）。

方針（2026-10）:
  - 自動化用プロファイル（~/.jarvis_state/chrome_* 等）は **処理終了で自動終了**
  - 日常の Google Chrome（デフォルトプロファイル）は触らない
  - Dock に残る主因は「終わったあと放置」→ auto_quit で解消
  - 作業中だけ一瞬アイコンが出ることがある（headed 必須の画面操作用）

  keep_alive=True または JARVIS_CDP_CHROME_KEEP_ALIVE=1 のときだけ終了しない。
"""
from __future__ import annotations

import atexit
import os
import signal
import socket
import subprocess
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
DEFAULT_CDP_PORT = 9223

# このプロセスで「終了時に閉じる」対象 (profile_resolved_str, port)
_AUTO_QUIT: set[tuple[str, int]] = set()
_ATEXIT_REGISTERED = False
_SIGNALS_HOOKED = False


def cdp_ready(port: int) -> bool:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(1)
            s.connect(("127.0.0.1", port))
        return True
    except OSError:
        return False


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


def collect_automation_chrome_pids(
    *,
    profile_dir: Path | None = None,
    port: int | None = None,
) -> list[int]:
    """自動化 Chrome の PID を集める（日常 Chrome は含めない）。"""
    pids: set[int] = set()
    if profile_dir is not None:
        prof = str(profile_dir.resolve())
        # user-data-dir=... またはパス断片
        pids.update(_pgrep_f(f"user-data-dir={prof}"))
        pids.update(_pgrep_f(f"user-data-dir=.*{profile_dir.name}"))
        # メインバイナリに限定し、Cursor 等の Electron を避ける
        for pid in list(pids):
            try:
                cmd = subprocess.check_output(
                    ["ps", "-p", str(pid), "-o", "command="], text=True
                ).strip()
            except subprocess.CalledProcessError:
                pids.discard(pid)
                continue
            if "/Applications/Google Chrome.app/" not in cmd:
                pids.discard(pid)
    if port is not None:
        for pid in _lsof_listen(port):
            try:
                cmd = subprocess.check_output(
                    ["ps", "-p", str(pid), "-o", "command="], text=True
                ).strip()
            except subprocess.CalledProcessError:
                continue
            if "/Applications/Google Chrome.app/" in cmd and "user-data-dir=" in cmd:
                # デフォルトプロファイルっぽいものは除外
                if "/Google/Chrome" in cmd and ".jarvis_state" not in cmd:
                    if "notebooklm" not in cmd and "playwright" not in cmd:
                        continue
                pids.add(pid)
    return sorted(pids)


def stop_cdp_chrome(
    profile_dir: Path | None = None,
    port: int | None = None,
    *,
    force: bool = True,
    quiet: bool = False,
) -> int:
    """当該プロファイル／ポートの自動化 Chrome を終了。終了した PID 数を返す。"""
    if profile_dir is None and port is None:
        return 0
    pids = collect_automation_chrome_pids(profile_dir=profile_dir, port=port)
    if not pids:
        return 0
    if not quiet:
        label = profile_dir.name if profile_dir else f"port:{port}"
        print(f"📎 自動化 Chrome を終了します ({label}: {pids})")
    sig = signal.SIGKILL if force else signal.SIGTERM
    for pid in pids:
        try:
            os.kill(pid, sig if force else signal.SIGTERM)
        except ProcessLookupError:
            pass
        except PermissionError:
            if not quiet:
                print(f"  skip pid={pid} (permission)")
    if not force:
        time.sleep(1.0)
        rem = collect_automation_chrome_pids(profile_dir=profile_dir, port=port)
        for pid in rem:
            try:
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
    else:
        time.sleep(0.4)
    return len(pids)


def _atexit_quit_all() -> None:
    for prof, port in list(_AUTO_QUIT):
        try:
            stop_cdp_chrome(Path(prof), port, force=True, quiet=True)
        except Exception:
            pass
    _AUTO_QUIT.clear()


def _ensure_hooks() -> None:
    global _ATEXIT_REGISTERED, _SIGNALS_HOOKED
    if not _ATEXIT_REGISTERED:
        atexit.register(_atexit_quit_all)
        _ATEXIT_REGISTERED = True
    if _SIGNALS_HOOKED:
        return

    def _wrap(signum: int) -> None:
        prev = signal.getsignal(signum)

        def _on_signal(signum2: int, frame: object) -> None:
            _atexit_quit_all()
            if callable(prev):
                prev(signum2, frame)
            elif prev == signal.SIG_DFL:
                signal.signal(signum2, signal.SIG_DFL)
                os.kill(os.getpid(), signum2)

        try:
            signal.signal(signum, _on_signal)
        except Exception:
            pass

    for sig in (signal.SIGINT, signal.SIGTERM):
        _wrap(sig)
    _SIGNALS_HOOKED = True


def _want_keep_alive(keep_alive: bool | None) -> bool:
    if keep_alive is True:
        return True
    if keep_alive is False:
        return False
    return os.environ.get("JARVIS_CDP_CHROME_KEEP_ALIVE", "").strip() in (
        "1",
        "true",
        "yes",
    )


def _register_auto_quit(profile: Path, port: int) -> None:
    _ensure_hooks()
    _AUTO_QUIT.add((str(profile.resolve()), port))


def start_cdp_chrome(
    port: int = DEFAULT_CDP_PORT,
    profile_dir: Path | None = None,
    start_url: str = "about:blank",
    *,
    keep_alive: bool | None = None,
    auto_quit: bool | None = None,
) -> None:
    """CDP Chrome を起動（または既存に接続）。

    既定ではこの Python プロセス終了時に当該プロファイルを自動終了する。
    残したいときだけ keep_alive=True（または環境変数）。
    """
    if not Path(CHROME).exists():
        raise RuntimeError(f"Google Chrome が見つかりません: {CHROME}")
    profile = Path(profile_dir or (Path.home() / ".jarvis_state" / "chrome_car_loan"))
    profile.mkdir(parents=True, exist_ok=True)

    # auto_quit は keep_alive の別名（False で keep）
    if auto_quit is False:
        keep = True
    elif auto_quit is True:
        keep = False
    else:
        keep = _want_keep_alive(keep_alive)

    if not keep:
        _register_auto_quit(profile, port)

    if cdp_ready(port):
        print(f"📎 既存の CDP Chrome を利用します (port {port})")
        if not keep:
            print("  （この処理の終了時に自動で閉じます）")
        return

    args = [
        CHROME,
        f"--remote-debugging-port={port}",
        f"--user-data-dir={profile}",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-session-crashed-bubble",
        start_url,
    ]
    print(f"📎 CDP Chrome を起動します (port {port}, profile {profile.name})")
    if not keep:
        print("  （終了時に自動で閉じます / Dock に残しません）")
    subprocess.Popen(
        args,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    for _ in range(40):
        if cdp_ready(port):
            time.sleep(0.8)
            print(f"📎 CDP 準備完了: http://127.0.0.1:{port}")
            return
        time.sleep(0.5)
    raise RuntimeError(f"CDP Chrome が port {port} で起動しませんでした")


@contextmanager
def cdp_chrome_session(
    port: int = DEFAULT_CDP_PORT,
    profile_dir: Path | None = None,
    start_url: str = "about:blank",
    *,
    keep_alive: bool | None = None,
) -> Iterator[None]:
    """起動〜必ず終了のセッション。新規コードはこちら推奨。"""
    profile = Path(profile_dir or (Path.home() / ".jarvis_state" / "chrome_car_loan"))
    start_cdp_chrome(port, profile, start_url, keep_alive=keep_alive)
    try:
        yield
    finally:
        if not _want_keep_alive(keep_alive):
            stop_cdp_chrome(profile, port, force=True)


def open_in_chrome(url: str) -> None:
    """日常 Chrome（デフォルトプロファイル）で URL を開く。自動化用ではない。"""
    if not Path(CHROME).exists():
        raise RuntimeError(f"Google Chrome が見つかりません: {CHROME}")
    subprocess.run(["open", "-a", "Google Chrome", url], check=True)
    print(f"📎 Chrome で開きました: {url}")
