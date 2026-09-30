#!/bin/zsh
# Vポイント定例（ウィンドウC: 付与サマリ＋cadence＋テイチャンdue）
# 自動できることのみ。OTP／Wallet は state の jarvis_asks に残す
set -euo pipefail
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PY="${HOME}/selenium_env/venv/bin/python"
LOG_DIR="${HOME}/Library/Logs/jarvis_vpoint_routine"
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
  "$PY" -u "${REPO_DIR}/scripts/jarvis_vpoint_routine.py" --apply --push
  echo "# end exit=$?"
} >>"$LOG" 2>&1
