#!/bin/zsh
# 314 業務品質監査 — 週次の機械チェック（土曜 9:00）。判断・修正は 9:30 の Claude 定期タスク
set -euo pipefail
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_DIR"
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"
set -a
# shellcheck disable=SC1091
source "$REPO_DIR/.env.jarvis_private"
set +a
PY="${JARVIS_PYTHON:-/Users/matsunomasaharu2/selenium_env/venv/bin/python}"
exec "$PY" "$REPO_DIR/scripts/jarvis_weekly_review_314.py" --post
