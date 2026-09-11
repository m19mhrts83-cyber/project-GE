#!/bin/zsh
# ETC 平日朝夕還元額の自動取得（毎月 20〜26日 09:30 JST）
# 公式: 利用月の翌月20日付与 → smile-etc から取って etc_monthly → /etc
set -euo pipefail
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PY="${HOME}/selenium_env/venv/bin/python"
LOG_DIR="${HOME}/Library/Logs/jarvis_etc_rebate"
mkdir -p "$LOG_DIR"
STAMP="$(date +%Y%m%d_%H%M%S)"
LOG="${LOG_DIR}/fetch_${STAMP}.log"

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
  "$PY" -u "${REPO_DIR}/scripts/jarvis_etc_rebate_fetch.py" --apply --push
  echo "# end exit=$?"
} >>"$LOG" 2>&1
