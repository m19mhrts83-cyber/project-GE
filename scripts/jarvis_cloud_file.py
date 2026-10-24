"""OneDrive／Google Drive（CloudStorage）上のファイルを安全に読む小さな共通関数。

macOS のファイルオンデマンドでは、まだダウンロードされていないプレースホルダを読むと
OSError [Errno 11] Resource deadlock avoided（EDEADLK）が出る。数秒後に再試行すると
読めることが多いが、読めなくても 1 ファイルのせいでジョブ全体を落とさない。

    from jarvis_cloud_file import read_text_cloud, copy_cloud

    text = read_text_cloud(path)        # 読めなければ None（stderr に 1 行）
    ok = copy_cloud(src, dst)           # 失敗なら False

関連: jarvis_energy_cf_collect.py（ローカルコピー経由で読む先行例）
"""

from __future__ import annotations

import shutil
import sys
import time
from pathlib import Path

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
