#!/usr/bin/env python3
"""CHRLINE-Patch 実行ラッパー（rich の再帰超過と INFO スパム対策）。

  cd ~/git-repos/line_unofficial_poc && ./run_patch.sh chrline_quiet.py \
      chrline_yoritoori_inbox_fetch.py --allow-qr-login --skip-open-chat

背景（2026-09-30）:
  CHRLINE の INFO/WARNING ログ（`got fullSyncResponse` / thrift の missing define fields）が
  大量に出ると、CHRLINE/logger.py の RichHandler が巨大テーブルを描画しようとして
  `RecursionError: maximum recursion depth exceeded` でバッチごと落ちる。
  → rich ハンドラを素の StreamHandler に置き換え、ログレベルを落として根本回避する。

環境変数:
  CHRLINE_LOG_LEVEL       … ERROR（既定）/ WARNING / INFO
  CHRLINE_RECURSION_LIMIT … 30000（既定）
"""
from __future__ import annotations

import logging
import os
import runpy
import sys

LEVEL = os.environ.get("CHRLINE_LOG_LEVEL", "ERROR").upper()
# 再帰上限は原則いじらない。上げすぎると C スタックを食い潰して
# RecursionError ではなく SIGSEGV（exit 139）で落ちる。
LIMIT = int(os.environ.get("CHRLINE_RECURSION_LIMIT", "0"))
if LIMIT > 0:
    sys.setrecursionlimit(LIMIT)

if len(sys.argv) < 2:
    print("usage: chrline_quiet.py <script.py> [args...]", file=sys.stderr)
    raise SystemExit(2)

target = sys.argv[1]
sys.argv = [target] + sys.argv[2:]

try:
    from CHRLINE.logger import root as chrline_root

    level_no = getattr(logging, LEVEL, logging.ERROR)
    chrline_root.setLevel(level_no)
    # rich の巨大テーブル描画を避けるため、ハンドラを素の stderr 出力に差し替える。
    # ロガー側のレベルが後から上書きされても効くよう、ハンドラ側にもフィルタを付ける。
    plain = logging.StreamHandler(sys.stderr)
    plain.setFormatter(logging.Formatter("%(name)s %(message)s"))
    plain.addFilter(lambda rec: rec.levelno >= level_no)
    chrline_root.handlers = [plain]
    print(f"# chrline_quiet: CHRLINE log level={LEVEL}, rich handler を除去", file=sys.stderr)
except Exception as e:  # noqa: BLE001
    print(f"# chrline_quiet: logger 抑制スキップ ({type(e).__name__}: {e})", file=sys.stderr)

runpy.run_path(target, run_name="__main__")
