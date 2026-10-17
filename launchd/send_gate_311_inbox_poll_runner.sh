#!/bin/zsh
# 311 経路A: input/ を拾ってゲート（Slack投稿）
set -euo pipefail
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
LOG_DIR="${HOME}/Library/Logs/jarvis_send_gate_311"
mkdir -p "$LOG_DIR"
PY="${HOME}/selenium_env/venv/bin/python"
cd "$REPO_DIR"
set -a
# shellcheck disable=SC1091
source "${REPO_DIR}/.env.jarvis_private"
set +a

if [[ "${JARVIS_SEND_GATE_311_POLL_DISABLE:-}" == "1" ]]; then
  echo "$(date '+%F %T') skip: JARVIS_SEND_GATE_311_POLL_DISABLE=1" >>"${LOG_DIR}/poll.log"
  exit 0
fi

{
  echo "======== $(date '+%F %T') ========"
  "$PY" "${REPO_DIR}/scripts/jarvis_send_gate_311.py" --from-inbox --post
} >>"${LOG_DIR}/poll.log" 2>>"${LOG_DIR}/poll.err.log"
