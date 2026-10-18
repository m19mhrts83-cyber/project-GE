#!/bin/zsh
# 315 連携健全性点検係 — Mac補完 日曜 21:45 JST（GHA 21:00 のあと）
# 検知→異常なら既知復旧1回→再点検→Slack #ops（未解決は #consult）
set -euo pipefail
# launchd の既定 PATH は /usr/bin:/bin:/usr/sbin:/sbin のみ。
# gh（$HOME/bin）等のローカル CLI が見えず WeStudy 点検が「確認不能」になるため明示する。
export PATH="$HOME/bin:$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:$PATH"
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
  "$PY" "${REPO_DIR}/scripts/jarvis_ops_health_315.py" \
    --remediate-once --post --mark-checked
  echo "# end exit=$?"
} >>"$LOG" 2>&1
