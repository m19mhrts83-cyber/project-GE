#!/bin/zsh
# main checkout を origin/main に追従（ff のみ・30分ごと）。ff できないときだけ #ops へ1日1回
set -euo pipefail
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
LOG_DIR="${HOME}/Library/Logs/jarvis_main_checkout_sync"
mkdir -p "$LOG_DIR"
export PATH="${HOME}/bin:/opt/homebrew/bin:/usr/local/bin:${PATH}"
cd "$REPO_DIR"
set -a
# shellcheck disable=SC1091
source "${REPO_DIR}/.env.jarvis_private"
set +a
PY="${HOME}/selenium_env/venv/bin/python"
[[ -x "$PY" ]] || PY="python3"
{
  echo "# $(date '+%Y-%m-%d %H:%M:%S %z')"
  "$PY" scripts/jarvis_main_checkout_sync.py --apply
} >>"${LOG_DIR}/sync.log" 2>&1
