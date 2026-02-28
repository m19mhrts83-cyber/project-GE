#!/bin/bash
# 画像テキスト索引を生成する。初回のみ venv 作成・パッケージインストールを行う。
cd "$(dirname "$0")"
BASE="$(pwd)"
VENV="$BASE/.venv_index"

if [[ ! -d "$VENV" ]]; then
  echo "初回: .venv_index を作成し、Pillow と pytesseract をインストールします..."
  python3 -m venv "$VENV"
  "$VENV/bin/pip" install -q --trusted-host pypi.org --trusted-host files.pythonhosted.org Pillow pytesseract
fi

"$VENV/bin/python" build_image_index.py "$@"
