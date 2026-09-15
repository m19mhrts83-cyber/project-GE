#!/bin/zsh
# グルコン WeStudy 投稿: KeepAlive 常駐 → jarvis_westudy_forum_post_watch.py
# queued が無いときは Playwright を立てずに idle
set -euo pipefail
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PY="${HOME}/selenium_env/venv/bin/python"
LOG_DIR="${HOME}/Library/Logs/jarvis_glucon"
mkdir -p "$LOG_DIR"

cd "$REPO_DIR"
if [[ -f "${REPO_DIR}/.env.jarvis_private" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "${REPO_DIR}/.env.jarvis_private"
  set +a
fi

exec "$PY" "${REPO_DIR}/scripts/jarvis_westudy_forum_post_watch.py"
