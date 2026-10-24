#!/bin/zsh
# GHA 定刻キック（10 分おき）。時刻が要る workflow を定刻に workflow_dispatch で起動する（AI なし）
set -euo pipefail
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_DIR"
# gh は ~/bin にある（launchd の PATH には入らない）
export PATH="$HOME/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"
PY="${JARVIS_PYTHON:-/Users/matsunomasaharu2/selenium_env/venv/bin/python}"
exec "$PY" "$REPO_DIR/scripts/jarvis_gha_precise_kick.py"
