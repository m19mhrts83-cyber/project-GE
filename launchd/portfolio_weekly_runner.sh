#!/bin/zsh
# 資産全体の週次 Web 収集（日曜 09:10 ＋ Mac 起動時 RunAtLoad ＋ 朝オープン取りこぼし）
# 成功済みの ISO 週は scripts 側でスキップ。手動は KURASHIFT ホームのボタン or --force。
# 複数 spawn の同時実行を flock で防ぐ（あかつき OTP 競合・成功結果の上書き防止）。
set -euo pipefail
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PY="${HOME}/selenium_env/venv/bin/python"
LOG_DIR="${HOME}/Library/Logs/jarvis_portfolio"
mkdir -p "$LOG_DIR"
STAMP="$(date +%Y%m%d_%H%M%S)"
LOG="${LOG_DIR}/weekly_${STAMP}.log"
LOCK="${LOG_DIR}/weekly.lock"

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

exec 9>"$LOCK"
if ! flock -n 9; then
  {
    echo "# start $(date '+%Y-%m-%d %H:%M:%S %z')"
    echo "# skip: another portfolio_weekly is already running (flock)"
    echo "# end exit=0"
  } >>"$LOG" 2>&1
  exit 0
fi

{
  echo "# start $(date '+%Y-%m-%d %H:%M:%S %z')"
  "$PY" -u "${REPO_DIR}/scripts/jarvis_portfolio_weekly.py"
  echo "# end exit=$?"
} >>"$LOG" 2>&1
