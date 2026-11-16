#!/usr/bin/env python3
"""業者台帳 YAML を書き換えたら、GHA 見守りが読む Secret へ自動で追従させる。

背景（2026-11-17）: 平日16時の GHA 見守り（kurashift-vendor-outreach-stall.yml）は
台帳を Secret KURASHIFT_*_VENDOR_LIST_B64 から読む。Mac で --mark しても Secret が
10/15 のまま残り、S9 の最終連絡日が古いまま報告され続けた。

使い方（各台帳スクリプトの __main__ から）:
    raise SystemExit(run_with_secret_sync(main, LIST_PATH, "KURASHIFT_MGMT_VENDOR_LIST_B64"))

- main() の前後で YAML の中身を比べ、変わった時だけ
  `gzip -9 | base64 | gh secret set <NAME>` と同じ処理をする。
- --dry-run・GHA 内（GITHUB_ACTIONS）・無効化 env のときは何もしない。
- 失敗しても台帳の書き込み結果（終了コード）は変えない（stderr に1行出すだけ）。
- Secret の値はログに出さない。

無効化: JARVIS_VENDOR_LIST_SECRET_SYNC_DISABLE=1
"""

from __future__ import annotations

import base64
import gzip
import hashlib
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Callable

DEFAULT_REPO = "m19mhrts83-cyber/project-GE"


def _digest(path: Path) -> str | None:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def _disabled() -> str | None:
    if "--dry-run" in sys.argv[1:]:
        return "dry-run"
    if (os.environ.get("GITHUB_ACTIONS") or "").strip().lower() == "true":
        return "github-actions"
    v = (os.environ.get("JARVIS_VENDOR_LIST_SECRET_SYNC_DISABLE") or "").strip().lower()
    if v in ("1", "true", "yes", "on"):
        return "disabled-by-env"
    return None


def sync_secret(path: Path, secret_name: str, *, repo: str | None = None) -> tuple[bool, str]:
    """YAML を gzip|base64 にして gh secret set。戻り値 (成功, 説明)。値は返さない。"""
    gh = shutil.which("gh") or ("/opt/homebrew/bin/gh" if Path("/opt/homebrew/bin/gh").exists() else None)
    if not gh:
        return False, "gh が見つからない"
    try:
        payload = base64.b64encode(gzip.compress(path.read_bytes(), compresslevel=9)).decode("ascii")
    except OSError as e:
        return False, f"台帳を読めない: {e.__class__.__name__}"
    target = repo or os.environ.get("JARVIS_VENDOR_LIST_SECRET_REPO") or DEFAULT_REPO
    try:
        cp = subprocess.run(
            [gh, "secret", "set", secret_name, "-R", target],
            input=payload,
            text=True,
            capture_output=True,
            timeout=60,
        )
    except (OSError, subprocess.TimeoutExpired) as e:
        return False, f"gh 実行失敗: {e.__class__.__name__}"
    if cp.returncode != 0:
        err = (cp.stderr or "").strip().splitlines()
        return False, f"gh secret set 失敗: {err[-1] if err else cp.returncode}"
    return True, f"{secret_name} を更新"


def run_with_secret_sync(main: Callable[[], int], list_path: Path, secret_name: str) -> int:
    before = _digest(list_path)
    rc = main()
    reason = _disabled()
    if reason:
        return rc
    after = _digest(list_path)
    if after is None or after == before:
        return rc
    ok, msg = sync_secret(list_path, secret_name)
    mark = "📎" if ok else "⚠️"
    print(f"{mark} secret sync: {msg}", file=sys.stderr)
    return rc


if __name__ == "__main__":
    # 手動追従: python scripts/jarvis_vendor_list_secret_sync.py config/kurashift_mgmt_vendor_list.yaml KURASHIFT_MGMT_VENDOR_LIST_B64
    if len(sys.argv) != 3:
        print("usage: jarvis_vendor_list_secret_sync.py <yaml> <SECRET_NAME>", file=sys.stderr)
        raise SystemExit(2)
    ok, msg = sync_secret(Path(sys.argv[1]), sys.argv[2])
    print(msg)
    raise SystemExit(0 if ok else 1)
