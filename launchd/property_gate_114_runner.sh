#!/bin/zsh
# 物件進行ゲート 114（Jarvis 不要・プログラム本線）
# Grok 取込のあと振分＋Slack。上限時もここが動いていれば Bカードが届く。
set -euo pipefail
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PY="${HOME}/selenium_env/venv/bin/python"
LOG_DIR="${HOME}/Library/Logs/jarvis_property_gate"
mkdir -p "$LOG_DIR"
STAMP="$(date +%Y%m%d_%H%M%S)"
LOG="${LOG_DIR}/gate114_${STAMP}.log"
cd "$REPO_DIR"
if [[ -f "${REPO_DIR}/.env.jarvis_private" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "${REPO_DIR}/.env.jarvis_private"
  set +a
fi
{
  echo "# property_gate_114 ${STAMP}"
  "$PY" -u "${REPO_DIR}/scripts/jarvis_property_gate_degraded.py"
} 2>&1 | tee "$LOG"
find "$LOG_DIR" -name 'gate114_*.log' -mtime +14 -delete 2>/dev/null || true
