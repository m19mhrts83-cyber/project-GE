#!/bin/zsh
# Jarvis トリアージ: Mac を開いた最初のタイミングでダッシュボードを自動オープン（1日1回）
set -euo pipefail
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PY="${HOME}/selenium_env/venv/bin/python"
LOG_DIR="${HOME}/Library/Logs/jarvis_night_triage"
mkdir -p "$LOG_DIR"
cd "$REPO_DIR"
if [[ -f "${REPO_DIR}/.env.jarvis_private" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "${REPO_DIR}/.env.jarvis_private"
  set +a
fi
exec "$PY" -u "${REPO_DIR}/scripts/jarvis_triage_morning_open.py" "$@"
