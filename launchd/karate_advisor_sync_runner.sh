#!/bin/zsh
# Jarvis: 空手アドバイザー（Grok Bot）自律リサーチ回収 runner
set -euo pipefail
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PY="${HOME}/selenium_env/venv/bin/python"
LOG_DIR="${HOME}/Library/Logs/jarvis_karate_advisor"
mkdir -p "$LOG_DIR"
STAMP="$(date +%Y%m%d_%H%M%S)"
LOG="${LOG_DIR}/karate_sync_${STAMP}.log"

cd "$REPO_DIR"
if [[ -f "${REPO_DIR}/.env.jarvis_private" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "${REPO_DIR}/.env.jarvis_private"
  set +a
fi

{
  echo "# start $(date '+%Y-%m-%d %H:%M:%S %z')"
  "$PY" "${REPO_DIR}/scripts/jarvis_karate_advisor_sync.py"
  echo "# end exit=$?"
} >>"$LOG" 2>&1

# ログ肥大化防止: 14日超を削除
find "$LOG_DIR" -name 'karate_sync_*.log' -mtime +14 -delete 2>/dev/null || true
