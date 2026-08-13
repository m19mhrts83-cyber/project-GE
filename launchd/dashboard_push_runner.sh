#!/bin/zsh
# Jarvis Dashboard → Supabase 日次 push（lanes/finance 含む）
# 先頭でカード引落ウォッチを更新し、situation_watch 経由でピンに載せる
set -euo pipefail
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PY="${HOME}/selenium_env/venv/bin/python"
LOG_DIR="${HOME}/Library/Logs/jarvis_dashboard"
mkdir -p "$LOG_DIR"
STAMP="$(date +%Y%m%d_%H%M%S)"
LOG="${LOG_DIR}/push_${STAMP}.log"

cd "$REPO_DIR"
if [[ -f "${REPO_DIR}/.env.jarvis_private" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "${REPO_DIR}/.env.jarvis_private"
  set +a
fi

{
  echo "# start $(date '+%Y-%m-%d %H:%M:%S %z')"
  # P0: カード引落収集（金額未確定なら Vpass も試す。失敗しても push は続ける）
  if ! "$PY" "${REPO_DIR}/scripts/jarvis_card_debit_watch.py" --fetch-vpass-if-pending; then
    echo "# card_debit_watch exit=$? (continue)"
  fi
  if ! "$PY" "${REPO_DIR}/scripts/jarvis_situation_watch.py"; then
    echo "# situation_watch exit=$? (continue)"
  fi
  "$PY" "${REPO_DIR}/scripts/jarvis_dashboard_push.py"
  echo "# end exit=$?"
} >>"$LOG" 2>&1
