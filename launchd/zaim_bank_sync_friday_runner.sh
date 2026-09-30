#!/bin/zsh
# Zaim 銀行連携ウォッチ（火・金）→ Zaim Watch runner（安全自動適用＋費目見直し通知＋watch push）
set -euo pipefail
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
LOG_DIR="${HOME}/Library/Logs/jarvis_zaim"
mkdir -p "$LOG_DIR"
PY="${HOME}/selenium_env/venv/bin/python"
STATE_DIR="${REPO_DIR}/.jarvis_state"
ENV_FILE="${REPO_DIR}/.env.jarvis_private"
LOCK_DIR="${LOG_DIR}/zaim_bank_sync_friday.lock"

ts="$(date '+%Y-%m-%dT%H:%M:%S%z')"
echo "[$ts] zaim_bank_sync_friday start" >>"${LOG_DIR}/bank_sync.out.log"

if ! mkdir "$LOCK_DIR" 2>/dev/null; then
  echo "[$ts] skip: already running" >>"${LOG_DIR}/bank_sync.out.log"
  exit 0
fi
trap 'rmdir "$LOCK_DIR" 2>/dev/null || true' EXIT INT TERM

if [[ -f "$ENV_FILE" ]]; then
  set +eu
  set -a
  emulate -R sh -c "source '${ENV_FILE}'" 2>>"${LOG_DIR}/env_source.err.log" || true
  set +a
  set -euo pipefail
fi

if [[ "${JARVIS_ZAIM_BANK_SYNC_DISABLE:-}" == "1" ]]; then
  echo "[$ts] disabled via JARVIS_ZAIM_BANK_SYNC_DISABLE" >>"${LOG_DIR}/bank_sync.out.log"
  exit 0
fi

cd "$REPO_DIR"
"$PY" scripts/jarvis_zaim_bank_sync_check.py --force-prompt --mark-prompted \
  >>"${LOG_DIR}/bank_sync.out.log" 2>>"${LOG_DIR}/bank_sync.err.log" || true

# Zaim Watch: 品質検知 → 安全な集計設定の自動適用 → changelog → watch push
# （finance は火・金 CSV 12:00 が本線。09:00 は二重取込直し＋費目見直し通知）
"$PY" scripts/jarvis_zaim_watch_runner.py --skip-finance \
  >>"${LOG_DIR}/bank_sync.out.log" 2>>"${LOG_DIR}/bank_sync.err.log" || true

# /zaim「今すぐ更新」キューがあれば check まで実行
"$PY" scripts/jarvis_zaim_refresh_queue_poll.py --apply \
  >>"${LOG_DIR}/bank_sync.out.log" 2>>"${LOG_DIR}/bank_sync.err.log" || true

# stale のみ連携更新（OTP が出たら失敗して止まる。黙って無限リトライしない）
if [[ "${JARVIS_ZAIM_BANK_AUTO_UPDATE:-1}" != "0" ]]; then
  "$PY" scripts/jarvis_zaim_bank_sync_manual.py --from-stale --headless \
    >>"${LOG_DIR}/bank_sync.out.log" 2>>"${LOG_DIR}/bank_sync.err.log" || true
  "$PY" scripts/jarvis_zaim_bank_sync_check.py \
    >>"${LOG_DIR}/bank_sync.out.log" 2>>"${LOG_DIR}/bank_sync.err.log" || true
  # 残留 stale / OTP 系は Todoist（dedupe あり）
  "$PY" scripts/jarvis_zaim_bank_notify.py \
    >>"${LOG_DIR}/bank_sync.out.log" 2>>"${LOG_DIR}/bank_sync.err.log" || true
fi

echo "[$(date '+%Y-%m-%dT%H:%M:%S%z')] zaim_bank_sync_friday done" >>"${LOG_DIR}/bank_sync.out.log"
