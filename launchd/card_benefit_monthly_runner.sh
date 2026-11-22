#!/bin/zsh
# 614 年間特典ウォッチ 月次（Olive 月次メール取込 → Zaim 概算 → Slack #report 短報）
# 停止: JARVIS_CARD_BENEFIT_DISABLE=1
set -euo pipefail
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PY="${HOME}/selenium_env/venv/bin/python"
LOG_DIR="${HOME}/Library/Logs/jarvis_card_benefit"
mkdir -p "$LOG_DIR"
STAMP="$(date +%Y%m%d_%H%M%S)"
LOG="${LOG_DIR}/run_${STAMP}.log"

cd "$REPO_DIR"
export PYTHONUNBUFFERED=1
if [[ -f "${REPO_DIR}/.env.jarvis_private" ]]; then
  set +e
  set -a
  # shellcheck disable=SC1091
  source "${REPO_DIR}/.env.jarvis_private" 2>>"${LOG_DIR}/env_source.err.log"
  set +a
  set -e
fi

{
  echo "# start $(date '+%Y-%m-%d %H:%M:%S %z')"
  set +e
  "$PY" -u "${REPO_DIR}/scripts/jarvis_card_benefit_monthly.py" --force
  rc=$?
  set -e
  echo "# end exit=${rc}"
} >>"$LOG" 2>&1
