#!/bin/zsh
# 313 閉じ漏れ検知（毎日 19:30）— 外で済んだのに Todoist に残っている件を Nody（/313?tab=misses）へ置く。
# 提案だけ。Todoist は触らない（閉じるのは本人が Nody で「済み」を選んだ件だけ。反映は GHA の cleanup reflect）。
set -euo pipefail
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PY="${HOME}/selenium_env/venv/bin/python"
cd "$REPO_DIR"
if [[ -f "${REPO_DIR}/.env.jarvis_private" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "${REPO_DIR}/.env.jarvis_private"
  set +a
fi
exec "$PY" "${REPO_DIR}/scripts/jarvis_todoist_313_done_elsewhere.py" --publish
