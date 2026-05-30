#!/bin/bash
# 後方互換ラッパー。正本は ~/selenium_env/setup.sh
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
TARGET="${SCRIPT_DIR}/../selenium_env/setup.sh"
if [[ -x "$TARGET" ]]; then
  exec "$TARGET"
fi
exec "$HOME/selenium_env/setup.sh"
