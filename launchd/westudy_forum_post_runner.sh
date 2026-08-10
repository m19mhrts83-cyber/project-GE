#!/bin/zsh
# グルコン: status=queued の下書きだけ WeStudy 投稿（Dashboard 確認済み前提）
# queued が無いときは worker が Playwright を立てずに終了する
set -euo pipefail
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PY="${HOME}/selenium_env/venv/bin/python"
LOG_DIR="${HOME}/Library/Logs/jarvis_glucon"
mkdir -p "$LOG_DIR"
STAMP="$(date +%Y%m%d_%H%M%S)"
LOG="${LOG_DIR}/westudy_post_${STAMP}.log"

cd "$REPO_DIR"
if [[ -f "${REPO_DIR}/.env.jarvis_private" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "${REPO_DIR}/.env.jarvis_private"
  set +a
fi

{
  echo "# start $(date '+%Y-%m-%d %H:%M:%S %z')"
  # Dashboard 確認済み（queued）のみ投稿
  "$PY" "${REPO_DIR}/scripts/jarvis_westudy_forum_post_worker.py" --i-confirm-post
  echo "# end exit=$?"
} >>"$LOG" 2>&1
