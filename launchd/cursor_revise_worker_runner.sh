#!/bin/zsh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
LOG_DIR="${HOME}/Library/Logs/jarvis_night_triage"
PY="${HOME}/selenium_env/venv/bin/python"

mkdir -p "$LOG_DIR"
cd "$REPO_DIR"
set -a
# shellcheck disable=SC1091
source "${REPO_DIR}/.env.jarvis_private"
set +a

# 下書き見直しキュー
"$PY" -u "${REPO_DIR}/scripts/jarvis_triage_cursor_revise_worker.py" "$@" || true
# タスク／ウォッチ「聞く」の Mac キュー
"$PY" -u "${REPO_DIR}/scripts/jarvis_card_cursor_ask_worker.py" "$@" || true
