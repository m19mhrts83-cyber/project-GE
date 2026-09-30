#!/bin/zsh
# 画面ロック解除を待ち、間隔ポーリング系 launchd を1回走らせる
set -euo pipefail
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PY="${HOME}/selenium_env/venv/bin/python"
LOG_DIR="${HOME}/Library/Logs/jarvis_screen_unlock"
mkdir -p "$LOG_DIR"
cd "$REPO_DIR"
if [[ -f "${REPO_DIR}/.env.jarvis_private" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "${REPO_DIR}/.env.jarvis_private"
  set +a
fi
exec "$PY" -u "${REPO_DIR}/scripts/jarvis_screen_unlock_catchup.py"
