#!/bin/zsh
# Todoistタスク処置（313）— 夜20:00 片付け runner
# 段階1: 旧 ✅／📅 2通 → 1通「313 片付け」3択
set -euo pipefail
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PY="${HOME}/selenium_env/venv/bin/python"
LOG_DIR="${HOME}/Library/Logs/jarvis_todoist_313_digest"
mkdir -p "$LOG_DIR"

cd "$REPO_DIR"
if [[ -f "${REPO_DIR}/.env.jarvis_private" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "${REPO_DIR}/.env.jarvis_private"
  set +a
fi

export TODOIST_313_AUTHOR="${TODOIST_313_AUTHOR:-FRIDAY}"

if [[ $# -gt 0 ]]; then
  # 手動: 従来 digest 引数を渡したいとき
  if [[ "${1:-}" == "--legacy-digest" ]]; then
    shift
    exec "$PY" "${REPO_DIR}/scripts/jarvis_todoist_313_digest.py" "$@"
  fi
  exec "$PY" "${REPO_DIR}/scripts/jarvis_todoist_313_cleanup.py" "$@"
fi

# 本線: 3択片付け1通
"$PY" "${REPO_DIR}/scripts/jarvis_todoist_313_cleanup.py"

# ついで: 外で済んだ候補（投稿せず state のみ）
"$PY" "${REPO_DIR}/scripts/jarvis_todoist_313_done_elsewhere.py" || true
