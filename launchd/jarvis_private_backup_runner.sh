#!/bin/zsh
# Jarvis Private 暗号化バックアップ（週次）
set -euo pipefail
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PY="${HOME}/selenium_env/venv/bin/python"
LOG_DIR="${HOME}/Library/Logs/jarvis_private_backup"
mkdir -p "$LOG_DIR"
STAMP="$(date +%Y%m%d_%H%M%S)"
LOG="${LOG_DIR}/backup_${STAMP}.log"

export PATH="${HOME}/bin:/opt/homebrew/bin:/usr/local/bin:${PATH}"
cd "$REPO_DIR"
export PYTHONUNBUFFERED=1

{
  echo "# start $(date '+%Y-%m-%d %H:%M:%S %z')"
  "$PY" -u "${REPO_DIR}/scripts/jarvis_private_backup.py" --backup
  echo "# end exit=$?"
} >>"$LOG" 2>&1
