#!/bin/zsh
# 定額AIの係: KeepAlive 常駐 → jarvis_flat_ai_worker.py（ダッシュボードの依頼箱 ai_jobs を処理）
set -euo pipefail
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PY="${HOME}/selenium_env/venv/bin/python"
export PATH="${HOME}/.local/bin:/opt/homebrew/bin:/usr/local/bin:${PATH}"

cd "$REPO_DIR"
if [[ -f "${REPO_DIR}/.env.jarvis_private" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "${REPO_DIR}/.env.jarvis_private"
  set +a
fi
# 従量課金の鍵は係に渡さない（claude はサブスクのログインで動かす）
unset ANTHROPIC_API_KEY OPENAI_API_KEY GEMINI_API_KEY

exec "$PY" -u "${REPO_DIR}/scripts/jarvis_flat_ai_worker.py"
