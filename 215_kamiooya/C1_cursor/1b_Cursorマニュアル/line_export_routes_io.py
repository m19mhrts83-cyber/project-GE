"""line_export_routes.yaml の読込（OneDrive が未ダウンロードで Errno 11 になる対策）。

読めたら「最後に読めたコピー」をローカル（非リポ）へ保存し、
OSError で読めない時は短く再試行 → なお失敗なら last_good を使う。
"""
from __future__ import annotations

import os
import time
from pathlib import Path

LAST_GOOD_MESSAGE = "# routes yaml: last_good を使用(OneDrive未取得)"
RETRY_COUNT = 3
RETRY_WAIT_SEC = 2.0


def last_good_path() -> Path:
    override = os.environ.get("LINE_EXPORT_ROUTES_LAST_GOOD")
    if override:
        return Path(override)
    return (
        Path.home()
        / "Library"
        / "Application Support"
        / "jarvis_line_export"
        / "line_export_routes.last_good.yaml"
    )


def _save_last_good(text: str, dest: Path) -> None:
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_name(dest.name + ".tmp")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        os.chmod(tmp, 0o600)
        os.replace(tmp, dest)
    except OSError:
        pass  # コピーできなくても本体の読込は成功扱い


def read_routes_text(path: Path, *, last_good: Path | None = None) -> str:
    """yaml の本文を返す。読込失敗時は last_good、それも無ければ元の OSError。"""
    dest = last_good or last_good_path()
    err: OSError | None = None
    for i in range(RETRY_COUNT + 1):
        try:
            text = Path(path).read_text(encoding="utf-8")
        except OSError as e:
            err = e
            if i < RETRY_COUNT:
                time.sleep(RETRY_WAIT_SEC)
            continue
        _save_last_good(text, dest)
        return text
    try:
        text = dest.read_text(encoding="utf-8")
    except OSError:
        assert err is not None
        raise err
    print(LAST_GOOD_MESSAGE, flush=True)
    return text
