#!/bin/zsh
# Journal週次 → Notion（日曜 08:00 ＋ Mac 起動時 RunAtLoad ＋ 朝オープン取りこぼし）
# 週区切りは金締（土〜金）。成功済み（日曜08:00以降）は scripts 側 --auto でスキップ。
set -euo pipefail
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PY="${HOME}/selenium_env/venv/bin/python"
LOG_DIR="${HOME}/Library/Logs/jarvis_family_journal"
mkdir -p "$LOG_DIR"
STAMP="$(date +%Y%m%d_%H%M%S)"
LOG="${LOG_DIR}/weekly_${STAMP}.log"

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
  "$PY" -u "${REPO_DIR}/scripts/jarvis_family_journal_weekly.py" --pull --apply --auto
  echo "# end exit=$?"
} >>"$LOG" 2>&1
