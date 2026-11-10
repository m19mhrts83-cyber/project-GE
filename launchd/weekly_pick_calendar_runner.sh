#!/bin/zsh
# 今週の9件（Nody /week）に出すカレンダー3週間分を sync_meta へ（日曜 16:30・毎朝 6:30）
set -euo pipefail
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_DIR"
[[ "${WEEKLY_PICK_CALENDAR_DISABLE:-0}" == "1" ]] && { echo "disabled"; exit 0; }
export PATH="$HOME/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"
emulate -R sh -c "set -a; . '${REPO_DIR}/.env.jarvis_private'; set +a" 2>/dev/null || true
PY="${JARVIS_PYTHON:-/Users/matsunomasaharu2/selenium_env/venv/bin/python}"
exec "$PY" "$REPO_DIR/scripts/jarvis_weekly_pick_calendar.py" --publish
