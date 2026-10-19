#!/bin/zsh
# 家族会議・週次（715 家族会議週次係 / FRIDAY）
# 日曜 21:30 本番、月曜 07:00 --retry。前週ページの複製は松野さん担当。
set -euo pipefail
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PY="${HOME}/selenium_env/venv/bin/python"
LOG_DIR="${HOME}/Library/Logs/friday_family_meeting_weekly"
mkdir -p "$LOG_DIR"

cd "$REPO_DIR"
export PYTHONUNBUFFERED=1
export PATH="${HOME}/.local/bin:${HOME}/.genspark-tool-cli/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"

if [[ -f "${REPO_DIR}/.env.jarvis_private" ]]; then
  set +e
  set -a
  # shellcheck disable=SC1091
  source "${REPO_DIR}/.env.jarvis_private" 2>>"${LOG_DIR}/env_source.err.log"
  set +a
  set -e
fi

STAMP="$(date +%Y%m%d_%H%M%S)"
LOG="${LOG_DIR}/run_${STAMP}.log"
{
  echo "# start $(date '+%Y-%m-%d %H:%M:%S %z') args=$*"
} >>"$LOG" 2>&1
set +e
"$PY" -u "${REPO_DIR}/scripts/friday_family_meeting_weekly.py" "$@" >>"$LOG" 2>&1
RC=$?
set -e
{
  echo "# end exit=${RC}"
} >>"$LOG" 2>&1
exit "${RC}"
