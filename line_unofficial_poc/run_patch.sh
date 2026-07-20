#!/usr/bin/env bash
# CHRLINE-Patch (.venv-patch) 実行ラッパー（経路2 / Square 401 復旧版）。
#
# パッチ版 CHRLINE は config のエンドポイント既定が localhost（デバッグプロキシ前提）
# のため、実 LINE ドメインを環境変数で固定してから Python を起動する。
#
# 使い方:
#   ./run_patch.sh chrline_patch_square_direct_probe.py --allow-qr-login
#   ./run_patch.sh chrline_square_probe_phase0.py --allow-qr-login
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY="$HERE/.venv-patch/bin/python"

if [[ ! -x "$PY" ]]; then
  echo "[run_patch] .venv-patch が見つかりません: $PY" >&2
  echo "[run_patch] 構築手順は docs/運用コマンド一覧.md の「CHRLINE-Patch（Square 401 復旧）」を参照" >&2
  exit 1
fi

export LINE_HOST_DOMAIN="${LINE_HOST_DOMAIN:-https://ga2.line.naver.jp}"
export LINE_OBS_DOMAIN="${LINE_OBS_DOMAIN:-https://obs.line-apps.com}"
export LINE_API_DOMAIN="${LINE_API_DOMAIN:-https://api.line.me}"
export LINE_ACCESS_DOMAIN="${LINE_ACCESS_DOMAIN:-https://access.line.me}"

exec "$PY" "$@"
