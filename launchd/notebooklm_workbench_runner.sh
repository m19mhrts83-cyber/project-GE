#!/bin/zsh
# NotebookLM 作業セットヘルパー（Finder＋NLM）常駐 runner
set -euo pipefail
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PY="${HOME}/selenium_env/venv/bin/python"
LOG_DIR="${HOME}/Library/Logs/jarvis_notebooklm"
mkdir -p "$LOG_DIR"
cd "$REPO_DIR"
if [[ -f "${REPO_DIR}/.env.jarvis_private" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "${REPO_DIR}/.env.jarvis_private"
  set +a
fi
exec "$PY" -u "${REPO_DIR}/scripts/jarvis_notebooklm_workbench_helper.py"
