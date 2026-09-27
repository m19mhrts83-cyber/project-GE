#!/bin/zsh
# Sunday 18:40 JST: write advisor weekly pack to Drive outbox (Grok 19:00 前)
set -euo pipefail
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_DIR"
set -a
# shellcheck disable=SC1091
source "${REPO_DIR}/.env.jarvis_private"
set +a
exec /Users/matsunomasaharu2/selenium_env/venv/bin/python \
  "${REPO_DIR}/scripts/jarvis_advisor_weekly_pack.py" --apply
