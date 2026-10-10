#!/bin/zsh
# 111 パートナー連絡整理係・夜枠（20:30 JST）
# CHRLINE＋公式エクスポート → 更新時のみ Slack #report
set -euo pipefail
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
LOG_DIR="${HOME}/Library/Logs/jarvis_partner_111_night"
mkdir -p "$LOG_DIR"
STAMP="$(date +%Y%m%d_%H%M%S)"
LOG="${LOG_DIR}/night_${STAMP}.log"

{
  echo "=== partner_111_night ${STAMP} ==="
  cd "$REPO_DIR"
  set -a
  # shellcheck disable=SC1091
  source "${REPO_DIR}/.env.jarvis_private"
  set +a
  # 無人起動ではブラウザを開かない（速度）
  export JARVIS_PARTNER_111_SKIP_DASHBOARD=1
  PY="${HOME}/selenium_env/venv/bin/python"
  if [[ ! -x "$PY" ]]; then
    PY="python3"
  fi
  "$PY" scripts/jarvis_partner_night_pipeline.py --apply --push
  echo "exit=$?"
} 2>&1 | tee -a "$LOG"
