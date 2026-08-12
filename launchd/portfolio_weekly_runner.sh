#!/bin/zsh
# 資産全体の週次 Web 収集（日曜 09:00 ＋ Mac 起動時 RunAtLoad ＋ 朝オープン取りこぼし）
# 成功済みの ISO 週は scripts 側でスキップ。手動は KURASHIFT ホームのボタン or --force。
set -euo pipefail
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PY="${HOME}/selenium_env/venv/bin/python"
LOG_DIR="${HOME}/Library/Logs/jarvis_portfolio"
mkdir -p "$LOG_DIR"
STAMP="$(date +%Y%m%d_%H%M%S)"
LOG="${LOG_DIR}/weekly_${STAMP}.log"

cd "$REPO_DIR"
export PYTHONUNBUFFERED=1
# .env は壊れた行があっても落とさない（本読込は Python 側 load_private_env）
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
  "$PY" -u "${REPO_DIR}/scripts/jarvis_portfolio_weekly.py"
  echo "# end exit=$?"
} >>"$LOG" 2>&1
