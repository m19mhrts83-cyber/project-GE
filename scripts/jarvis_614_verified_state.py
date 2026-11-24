#!/usr/bin/env python3
"""614 ポイント・還元ウォッチ — state の読み書きを「読み戻して確かめる」ための共通部品（P0・工程16/28）。

  load_json_strict   存在しない→{}／存在するのに読めない・dict でない→StateReadError（{} にして上書きしない）
  save_json_verified tmp 書込→置換→読み戻し照合。不一致なら取得済みデータを pending に残し、
                     保存だけ最大 retries 回やり直す（外部サイトは取り直さない）
  file_lock          同時起動の排他（flock・非ブロッキング）

秘密・実額はここでは扱わない（渡された dict をそのまま書くだけ。ログにも値を出さない）。
"""
from __future__ import annotations

import contextlib
import fcntl
import json
import os
import shutil
from pathlib import Path
from typing import Any, Callable, Iterator


class StateReadError(RuntimeError):
    """state ファイルはあるのに読めない（破損・形式違い）。安全側で止める。"""


class LockBusy(RuntimeError):
    """別の実行が排他ロックを持っている。"""


def load_json_strict(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        raise StateReadError(f"{path.name} を読めません（{type(e).__name__}）") from e
    if not isinstance(data, dict):
        raise StateReadError(f"{path.name} の形式が想定外です（dict ではない）")
    return data


def roundtrip(data: dict[str, Any]) -> dict[str, Any]:
    """JSON に書いて読んだ時の姿（tuple→list 等）。照合の期待値に使う。"""
    return json.loads(json.dumps(data, ensure_ascii=False))


def _default_verify(read_back: dict[str, Any], expected: dict[str, Any]) -> list[str]:
    if read_back == expected:
        return []
    keys = sorted(
        k for k in set(read_back) | set(expected) if read_back.get(k) != expected.get(k)
    )
    return [f"不一致: {', '.join(keys[:8])}"]


def _write_atomic(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    payload = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    with tmp.open("w", encoding="utf-8") as f:
        f.write(payload)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def _write_pending(pending: Path | None, data: dict[str, Any]) -> None:
    if pending is None:
        return
    try:
        pending.parent.mkdir(parents=True, exist_ok=True)
        _write_atomic(pending, data)
        os.chmod(pending, 0o600)
    except OSError:
        pass  # 一時保持に失敗しても本線の失敗扱いは変えない


def save_json_verified(
    path: Path,
    data: dict[str, Any],
    *,
    verify: Callable[[dict[str, Any], dict[str, Any]], list[str]] | None = None,
    pending_path: Path | None = None,
    retries: int = 1,
) -> dict[str, Any]:
    """書いて読み戻し、照合する。返り値: {"ok": bool, "attempts": int, "errors": [..]}。

    失敗時は data を pending_path（非公開の state 領域）へ残す。外部取得はやり直さず保存だけ retries 回。
    成功したら pending は消す。直前の正常ファイルは .bak に残す（読めた時だけ）。"""
    check = verify or _default_verify
    expected = roundtrip(data)
    errors: list[str] = []
    attempts = 0
    for attempt in range(retries + 1):
        attempts = attempt + 1
        try:
            if path.is_file():
                try:
                    json.loads(path.read_text(encoding="utf-8"))
                    shutil.copy2(path, path.with_name(path.name + ".bak"))
                except (OSError, json.JSONDecodeError):
                    pass  # 壊れたファイルを .bak で正常版に上書きしない
            _write_atomic(path, data)
            read_back = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(read_back, dict):
                errors = check(read_back, expected)
            else:
                errors = ["読み戻した形式が想定外"]
        except (OSError, json.JSONDecodeError) as e:
            errors = [f"保存/読戻しエラー（{type(e).__name__}）"]
        if not errors:
            if pending_path is not None:
                with contextlib.suppress(OSError):
                    pending_path.unlink()
            return {"ok": True, "attempts": attempts, "errors": []}
        _write_pending(pending_path, data)
    return {"ok": False, "attempts": attempts, "errors": errors}


@contextlib.contextmanager
def file_lock(path: Path) -> Iterator[None]:
    """同時起動を防ぐ。取れなければ LockBusy。プロセス終了で OS が解放する（途中終了でも残らない）。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as e:
            raise LockBusy(str(path.name)) from e
        yield
    finally:
        with contextlib.suppress(OSError):
            fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)
