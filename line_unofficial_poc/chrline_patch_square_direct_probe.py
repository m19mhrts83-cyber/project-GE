#!/usr/bin/env python3
"""
CHRLINE-Patch 用の最小 Square 疎通検証（経路2）。

can_use_square の遅延評価を回避し、fetchSquareChatEvents を直接呼ぶ。
実行は .venv-patch + 実ドメイン環境変数で行う（運用コマンド一覧 §4 参照）。
"""
from __future__ import annotations

import os
import subprocess
import sys

from chrline_client_utils import (
    DEFAULT_SQUARE_PROBE_MID,
    DEFAULT_SQUARE_PROBE_THREAD_MID,
    build_logged_in_client,
    save_root_from_env,
)


def _try(label: str, fn) -> bool:
    try:
        res = fn()
        events = getattr(res, "events", None)
        n = len(events) if events is not None else "?"
        print(f"# direct probe [{label}]: OK events={n}")
        return True
    except Exception as exc:  # noqa: BLE001
        print(f"# direct probe [{label}]: NG {type(exc).__name__}: {str(exc)[:200]}")
        return False


def main() -> int:
    allow_qr = "--allow-qr-login" in sys.argv
    reuse_only = "--reuse-only" in sys.argv  # 子プロセス用: QR 禁止で保存トークンのみ
    save_root = save_root_from_env()
    cl = build_logged_in_client(save_root, allow_qr_login=allow_qr and not reuse_only)

    main_ok = _try(
        "main fetchSquareChatEvents",
        lambda: cl.fetchSquareChatEvents(DEFAULT_SQUARE_PROBE_MID, limit=5),
    )
    thread_ok = _try(
        "thread fetchSquareChatEvents",
        lambda: cl.fetchSquareChatEvents(
            DEFAULT_SQUARE_PROBE_MID, limit=5, threadMid=DEFAULT_SQUARE_PROBE_THREAD_MID
        ),
    )
    joined_ok = _try("getJoinedSquares", lambda: cl.getJoinedSquares(limit=5))
    tag = "child(reuse-token)" if reuse_only else "parent"
    print(f"# direct probe summary [{tag}]: main={main_ok} thread={thread_ok} joined={joined_ok}")

    tokens_dir = save_root / ".tokens"
    n_tokens = len(list(tokens_dir.iterdir())) if tokens_dir.is_dir() else 0
    print(f"# saved tokens in .tokens: {n_tokens}")

    # 親でトークン保存が確認できたら、子プロセスで QR 無し再利用を検証（トークン永続性）
    if not reuse_only and (main_ok and thread_ok) and n_tokens > 0:
        print("# --- 子プロセスで保存トークン再利用テスト（QR 無し） ---")
        rc = subprocess.call([sys.executable, __file__, "--reuse-only"], env=dict(os.environ))
        print(f"# child exit code: {rc} (0=保存トークンで再接続OK)")

    return 0 if (main_ok and thread_ok) else 1


if __name__ == "__main__":
    raise SystemExit(main())
