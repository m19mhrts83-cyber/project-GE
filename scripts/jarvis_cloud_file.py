"""OneDrive／Google Drive（CloudStorage）上のファイルを安全に読む小さな共通関数。

macOS のファイルオンデマンドでは、まだダウンロードされていないプレースホルダを読むと
OSError [Errno 11] Resource deadlock avoided（EDEADLK）が出る。数秒後に再試行すると
読めることが多いが、読めなくても 1 ファイルのせいでジョブ全体を落とさない。

    from jarvis_cloud_file import read_text_cloud, copy_cloud

    text = read_text_cloud(path)        # 読めなければ None（stderr に 1 行）
    ok = copy_cloud(src, dst)           # 失敗なら False

関連: jarvis_energy_cf_collect.py（ローカルコピー経由で読む先行例）

launchd から起動したプロセスは「未ダウンロードのファイルを取りに行く」設定が OFF
（getiopolicy_np = 1）で始まり、何度再試行しても EDEADLK になる（ターミナルは ON = 2）。
このモジュールを import した時点でプロセスの設定を ON にする（2026-11-14、311 が
10/24〜11/14 に同じ下書きで止まり続けた原因）。
"""

from __future__ import annotations

import shutil
import sys
import time
from pathlib import Path

# <sys/resource.h>
_IOPOL_TYPE_VFS_MATERIALIZE_DATALESS_FILES = 3
_IOPOL_SCOPE_PROCESS = 0
_IOPOL_MATERIALIZE_DATALESS_FILES_ON = 2


def enable_dataless_materialization() -> bool:
    """macOS: このプロセスで Drive／OneDrive の未ダウンロードファイルを読めるようにする。"""
    if sys.platform != "darwin":
        return False
    try:
        import ctypes

        libc = ctypes.CDLL(None, use_errno=True)
        rc = libc.setiopolicy_np(
            _IOPOL_TYPE_VFS_MATERIALIZE_DATALESS_FILES,
            _IOPOL_SCOPE_PROCESS,
            _IOPOL_MATERIALIZE_DATALESS_FILES_ON,
        )
        return rc == 0
    except Exception:  # noqa: BLE001 — 失敗しても従来どおり再試行で動く
        return False


enable_dataless_materialization()

DEFAULT_ATTEMPTS = 3
DEFAULT_WAIT_SEC = 2.0


def read_text_cloud(
    path: Path,
    *,
    encoding: str = "utf-8",
    errors: str = "replace",
    attempts: int = DEFAULT_ATTEMPTS,
    wait_sec: float = DEFAULT_WAIT_SEC,
) -> str | None:
    last: OSError | None = None
    for i in range(max(1, attempts)):
        try:
            return Path(path).read_text(encoding=encoding, errors=errors)
        except FileNotFoundError:
            return None
        except OSError as exc:
            last = exc
            if i + 1 < attempts:
                time.sleep(wait_sec)
    print(f"# cloud read skip: {path.name}: {last}", file=sys.stderr)
    return None


def copy_cloud(
    src: Path,
    dst: Path,
    *,
    attempts: int = DEFAULT_ATTEMPTS,
    wait_sec: float = DEFAULT_WAIT_SEC,
) -> bool:
    last: OSError | None = None
    for i in range(max(1, attempts)):
        try:
            shutil.copy2(src, dst)
            return True
        except OSError as exc:
            last = exc
            if i + 1 < attempts:
                time.sleep(wait_sec)
    print(f"# cloud copy skip: {src.name}: {last}", file=sys.stderr)
    return False
