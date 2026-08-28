#!/bin/zsh
# 朝の天気＋カレンダー → outbox_to_teams/weather/（Grok 6:30 より前）
set -euo pipefail
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PY="${HOME}/selenium_env/venv/bin/python"
LOG_DIR="${HOME}/Library/Logs/jarvis_weather"
mkdir -p "$LOG_DIR"
STAMP="$(date +%Y%m%d_%H%M%S)"
LOG="${LOG_DIR}/brief_${STAMP}.log"
cd "$REPO_DIR"
if [[ -f "${REPO_DIR}/.env.jarvis_private" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "${REPO_DIR}/.env.jarvis_private"
  set +a
fi
{
  echo "# jarvis_weather_morning_brief ${STAMP}"
  "$PY" -u "${REPO_DIR}/scripts/jarvis_weather_morning_brief.py"
} 2>&1 | tee "$LOG"
find "$LOG_DIR" -name 'brief_*.log' -mtime +14 -delete 2>/dev/null || true
