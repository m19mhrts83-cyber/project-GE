#!/bin/zsh
# 211 返信案内下書き係 — Mac 保険用朝便（heuristic・LLMなし）
# 本線は GHA jarvis-reply-draft-211.yml（Graph）。安定後は uninstall 可。
set -euo pipefail
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
LOG_DIR="${HOME}/Library/Logs/jarvis_reply_draft_211"
mkdir -p "$LOG_DIR"
cd "$REPO_DIR"
set -a
# shellcheck disable=SC1091
source "${REPO_DIR}/.env.jarvis_private"
set +a
PY="${HOME}/selenium_env/venv/bin/python"
exec "$PY" "${REPO_DIR}/scripts/jarvis_reply_draft_211.py" --morning --with-fetch "$@"
