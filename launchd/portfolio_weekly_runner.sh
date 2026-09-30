#!/bin/zsh
# 資産全体の週次 Web 収集（日曜 09:10 ＋ Mac 起動時 RunAtLoad ＋ 朝オープン取りこぼし）
# 成功済みの ISO 週は scripts 側でスキップ。手動は KURASHIFT ホームのボタン or --force。
# 複数 spawn の同時実行を防ぐ（あかつき OTP 競合・成功結果の上書き防止）。
# macOS 標準に flock コマンドは無いため mkdir ロックを使う（2026-09-30 修正）。
set -euo pipefail
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PY="${HOME}/selenium_env/venv/bin/python"
LOG_DIR="${HOME}/Library/Logs/jarvis_portfolio"
mkdir -p "$LOG_DIR"
STAMP="$(date +%Y%m%d_%H%M%S)"
LOG="${LOG_DIR}/weekly_${STAMP}.log"
# 旧 flock 用の空ファイルが残っていれば掃除（mkdir ロックは .d ディレクトリ）
if [[ -f "${LOG_DIR}/weekly.lock" ]]; then rm -f "${LOG_DIR}/weekly.lock"; fi
LOCK_DIR="${LOG_DIR}/weekly.lock.d"

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

# mkdir は原子的。多重起動は後発を skip。stale（6時間超）は回収する。
acquired=0
if mkdir "$LOCK_DIR" 2>/dev/null; then
  acquired=1
elif [[ -d "$LOCK_DIR" ]]; then
  age=$(( $(date +%s) - $(stat -f %m "$LOCK_DIR" 2>/dev/null || echo 0) ))
  if (( age > 21600 )); then
    rm -rf "$LOCK_DIR"
    if mkdir "$LOCK_DIR" 2>/dev/null; then acquired=1; fi
  fi
fi
if (( acquired == 0 )); then
  {
    echo "# start $(date '+%Y-%m-%d %H:%M:%S %z')"
    echo "# skip: another portfolio_weekly is already running (mkdir lock)"
    echo "# end exit=0"
  } >>"$LOG" 2>&1
  exit 0
fi
trap 'rm -rf "$LOCK_DIR"' EXIT INT TERM

{
  echo "# start $(date '+%Y-%m-%d %H:%M:%S %z')"
  "$PY" -u "${REPO_DIR}/scripts/jarvis_portfolio_weekly.py"
  echo "# end exit=$?"
} >>"$LOG" 2>&1
