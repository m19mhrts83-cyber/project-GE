#!/bin/zsh
# 317 コメント起動 — Mac 本線（300秒間隔）
set -euo pipefail
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_DIR"
set -a
# shellcheck disable=SC1091
source "$REPO_DIR/.env.jarvis_private"
set +a
PY="${JARVIS_PYTHON:-/Users/matsunomasaharu2/selenium_env/venv/bin/python}"
exec "$PY" "$REPO_DIR/scripts/jarvis_comment_dispatch.py" --apply
