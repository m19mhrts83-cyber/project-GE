#!/bin/zsh
# AIエージェントチーム — Drive ★AIエージェントチーム へ文書・成果物・ルールを写す（毎日 6:10）
set -euo pipefail
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_DIR"
# #ops 通知（競合検知）用に Webhook を読む。値は出さない
if [[ -f "$REPO_DIR/.env.jarvis_private" ]]; then set -a; source "$REPO_DIR/.env.jarvis_private" >/dev/null 2>&1; set +a; fi
PY="${JARVIS_PYTHON:-/Users/matsunomasaharu2/selenium_env/venv/bin/python}"
exec "$PY" "$REPO_DIR/scripts/jarvis_agent_team_drive_sync.py"
