#!/bin/zsh
# Todoist完了候補確認（313）— 夜20:00のL1ダイジェスト runner
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

# FRIDAY 実行＝コメント先頭を【FRIDAY】にする（既定は Jarvis）
export TODOIST_313_AUTHOR="${TODOIST_313_AUTHOR:-FRIDAY}"

# 確認のみの自動 close はしない（L1＝見るだけ／close は人の「閉じて N」）
exec "$PY" "${REPO_DIR}/scripts/jarvis_todoist_313_digest.py" "$@"
