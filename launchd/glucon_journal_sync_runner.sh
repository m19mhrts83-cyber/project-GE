#!/bin/zsh
# グルコン: ★Journal 神大家抜粋 → Supabase + 提出期限ウォッチ更新 + watch push
set -euo pipefail
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PY="${HOME}/selenium_env/venv/bin/python"
LOG_DIR="${HOME}/Library/Logs/jarvis_glucon"
mkdir -p "$LOG_DIR"
STAMP="$(date +%Y%m%d_%H%M%S)"
LOG="${LOG_DIR}/journal_sync_${STAMP}.log"

cd "$REPO_DIR"
if [[ -f "${REPO_DIR}/.env.jarvis_private" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "${REPO_DIR}/.env.jarvis_private"
  set +a
fi

{
  echo "# start $(date '+%Y-%m-%d %H:%M:%S %z')"
  "$PY" "${REPO_DIR}/scripts/jarvis_glucon_journal_sync.py" --days 90
  "$PY" "${REPO_DIR}/scripts/jarvis_glucon_report_check.py" --mark-checked
  "$PY" "${REPO_DIR}/scripts/jarvis_dashboard_push.py" --watch-only || true
  echo "# end exit=$?"
} >>"$LOG" 2>&1
