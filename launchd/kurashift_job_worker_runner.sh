#!/bin/zsh
# KURASHIFT: queued jobs を処理（15分ごと）
set -euo pipefail
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PY="${HOME}/selenium_env/venv/bin/python"
LOG_DIR="${HOME}/Library/Logs/jarvis_kurashift"
mkdir -p "$LOG_DIR"
STAMP="$(date +%Y%m%d_%H%M%S)"
LOG="${LOG_DIR}/worker_${STAMP}.log"

cd "$REPO_DIR"
if [[ -f "${REPO_DIR}/.env.jarvis_private" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "${REPO_DIR}/.env.jarvis_private"
  set +a
fi

{
  echo "# start $(date '+%Y-%m-%d %H:%M:%S %z')"
  "$PY" "${REPO_DIR}/scripts/jarvis_kurashift_job_worker.py" --limit 8
  echo "# end exit=$?"
} >>"$LOG" 2>&1

# 古いログを間引き（30日超）
find "$LOG_DIR" -name 'worker_*.log' -mtime +30 -delete 2>/dev/null || true
