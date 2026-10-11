#!/bin/zsh
# 315 連携健全性点検係 — 日曜 09:15 JST（WeStudy 08:00 のあと・ずらし）
set -euo pipefail
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PY="${HOME}/selenium_env/venv/bin/python"
LOG_DIR="${HOME}/Library/Logs/jarvis_ops_health_315"
mkdir -p "$LOG_DIR"
STAMP="$(date +%Y%m%d_%H%M%S)"
LOG="${LOG_DIR}/run_${STAMP}.log"

cd "$REPO_DIR"
if [[ -f "${REPO_DIR}/.env.jarvis_private" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "${REPO_DIR}/.env.jarvis_private"
  set +a
fi

if [[ "${JARVIS_OPS_HEALTH_315_DISABLE:-}" == "1" ]]; then
  echo "# disabled JARVIS_OPS_HEALTH_315_DISABLE=1" >>"$LOG"
  exit 0
fi

{
  echo "# start $(date '+%Y-%m-%d %H:%M:%S %z')"
  "$PY" "${REPO_DIR}/scripts/jarvis_ops_health_315.py" --post --mark-checked
  echo "# end exit=$?"
} >>"$LOG" 2>&1
