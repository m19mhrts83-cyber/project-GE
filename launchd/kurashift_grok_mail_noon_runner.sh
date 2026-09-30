#!/bin/zsh
# 11:00 JST 帯: estate `[Grok調査]` を --grok-only --apply で追撃取込
# （朝バンドルの1日1回制限後に届く S1 分を拾う。Mac 代替／補完用）
set -euo pipefail
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PY="${HOME}/selenium_env/venv/bin/python"
LOG_DIR="${HOME}/Library/Logs/jarvis_kurashift"
mkdir -p "$LOG_DIR"
STAMP="$(date +%Y%m%d_%H%M%S)"
LOG="${LOG_DIR}/grok_mail_noon_${STAMP}.log"
cd "$REPO_DIR"
if [[ -f "${REPO_DIR}/.env.jarvis_private" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "${REPO_DIR}/.env.jarvis_private"
  set +a
fi
{
  echo "# kurashift_grok_mail_noon ${STAMP}"
  "$PY" -u "${REPO_DIR}/scripts/jarvis_kurashift_property_mail_match.py" --grok-only --apply
} 2>&1 | tee "$LOG"
find "$LOG_DIR" -name 'grok_mail_noon_*.log' -mtime +14 -delete 2>/dev/null || true
