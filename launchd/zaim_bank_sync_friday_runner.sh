#!/bin/zsh
# Zaim 銀行連携ウォッチ（金曜）→ Zaim Watch runner（安全自動適用＋watch push）
set -euo pipefail
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
LOG_DIR="${HOME}/Library/Logs/jarvis_zaim"
mkdir -p "$LOG_DIR"
PY="${HOME}/selenium_env/venv/bin/python"
STATE_DIR="${REPO_DIR}/.jarvis_state"
ENV_FILE="${REPO_DIR}/.env.jarvis_private"

ts="$(date '+%Y-%m-%dT%H:%M:%S%z')"
echo "[$ts] zaim_bank_sync_friday start" >>"${LOG_DIR}/bank_sync.out.log"

if [[ -f "$ENV_FILE" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$ENV_FILE"
  set +a
fi

if [[ "${JARVIS_ZAIM_BANK_SYNC_DISABLE:-}" == "1" ]]; then
  echo "[$ts] disabled via JARVIS_ZAIM_BANK_SYNC_DISABLE" >>"${LOG_DIR}/bank_sync.out.log"
  exit 0
fi

cd "$REPO_DIR"
"$PY" scripts/jarvis_zaim_bank_sync_check.py --force-prompt --mark-prompted \
  >>"${LOG_DIR}/bank_sync.out.log" 2>>"${LOG_DIR}/bank_sync.err.log" || true

# Zaim Watch: 品質検知 → 安全な集計設定の自動適用 → changelog → watch push
# （finance は土曜 CSV 週次が本線。金曜は二重取込直し中心）
"$PY" scripts/jarvis_zaim_watch_runner.py --skip-finance \
  >>"${LOG_DIR}/bank_sync.out.log" 2>>"${LOG_DIR}/bank_sync.err.log" || true

echo "[$(date '+%Y-%m-%dT%H:%M:%S%z')] zaim_bank_sync_friday done" >>"${LOG_DIR}/bank_sync.out.log"
