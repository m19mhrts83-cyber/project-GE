#!/bin/zsh
# コミュニケーション台帳の機械の予備（GHA が止まったときだけ代走）。判断は scripts/jarvis_comm_hub_backup.py。
set -uo pipefail
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PY="${HOME}/selenium_env/venv/bin/python"
LOG_DIR="${HOME}/Library/Logs/jarvis_comm_hub_backup"
mkdir -p "$LOG_DIR"
cd "$REPO_DIR"
find "$LOG_DIR" -name 'backup_*.log' -mtime +30 -delete 2>/dev/null || true

PRIVATE_ENV="${HOME}/git-repos/.env.jarvis_private"
[[ -f "$PRIVATE_ENV" ]] || PRIVATE_ENV="${REPO_DIR}/.env.jarvis_private"
if [[ ! -f "$PRIVATE_ENV" ]]; then
  echo "private environment file is missing" >&2
  exit 2
fi
set -a
# shellcheck disable=SC1091
source "$PRIVATE_ENV"
set +a

LOG="${LOG_DIR}/backup_$(date +%Y%m%d_%H%M%S).log"
{
  echo "# start $(date '+%Y-%m-%d %H:%M:%S %z')"
  "$PY" "${REPO_DIR}/scripts/jarvis_comm_hub_backup.py"
  RC=$?
  echo "# end exit=${RC}"
} >>"$LOG" 2>&1
exit "${RC:-0}"
