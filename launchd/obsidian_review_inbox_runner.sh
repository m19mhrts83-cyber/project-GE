#!/bin/zsh
# Pull confirmed ChatGPT reviews to the local Obsidian Vault and existing OGD sync.
set -euo pipefail
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PY="${HOME}/selenium_env/venv/bin/python"
LOG_DIR="${HOME}/Library/Logs/jarvis_obsidian_review"
mkdir -p "$LOG_DIR"
cd "$REPO_DIR"

if [[ -f "${REPO_DIR}/.env.jarvis_private" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "${REPO_DIR}/.env.jarvis_private"
  set +a
fi

STAMP="$(date +%Y%m%d_%H%M%S)"
LOG="${LOG_DIR}/inbox_${STAMP}.log"
{
  echo "# start $(date '+%Y-%m-%d %H:%M:%S %z')"
  if "$PY" "${REPO_DIR}/scripts/jarvis_obsidian_review_inbox.py"; then
    RC=0
  else
    RC=$?
  fi
  echo "# end exit=${RC}"
} >>"$LOG" 2>&1
exit "$RC"
find "$LOG_DIR" -name 'inbox_*.log' -mtime +14 -delete 2>/dev/null || true
