#!/bin/zsh
# 815 オプチャ: MD差分取込 → kamiooya-qa DB → ダッシュボード投影
# CHRLINE / OneDrive 正本必須 → launchd（Mac）本線
set -euo pipefail
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
POC="${REPO_DIR}/line_unofficial_poc"
PY="${HOME}/selenium_env/venv/bin/python"
LOG_DIR="${HOME}/Library/Logs/jarvis_openchat_sync"
mkdir -p "$LOG_DIR"
STAMP="$(date +%Y%m%d_%H%M%S)"
LOG="${LOG_DIR}/sync_${STAMP}.log"
PAUSE="${POC}/launchd/open_chat_watch_pause.sh"
RESUME="${POC}/launchd/open_chat_watch_resume.sh"

cd "$REPO_DIR"
if [[ -f "${REPO_DIR}/.env.jarvis_private" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "${REPO_DIR}/.env.jarvis_private"
  set +a
fi

{
  echo "# start $(date '+%Y-%m-%d %H:%M:%S %z')"

  # Mac版LINE 競合ガード
  if pgrep -f 'application\.jp\.naver\.line\.mac|/Applications/LINE\.app' >/dev/null 2>&1; then
    echo "# abort: Mac版LINE 起動中（CHRLINE競合）"
    exit 3
  fi

  if [[ -x "$PAUSE" ]]; then
    "$PAUSE" || true
  fi

  # メイン差分（スレは常時監視が本線。ここでは軽量にメイン中心）
  (
    cd "$POC"
    ./run_patch.sh chrline_open_chat_to_md.py --no-threads
  )
  md_rc=$?

  # MD → kamiooya-qa.line_openchat_logs（staging）＋ Grok共有
  "$PY" "${REPO_DIR}/scripts/jarvis_kurashift_openchat_sync.py" --apply --export-grok
  db_rc=$?

  # ダッシュボード /openchat（digest + thread health）
  "$PY" "${REPO_DIR}/scripts/jarvis_openchat_digest.py" --push || true
  "$PY" "${REPO_DIR}/scripts/jarvis_openchat_thread_health.py" --push || true

  if [[ -x "$RESUME" ]]; then
    "$RESUME" || true
  fi

  echo "# end md_rc=${md_rc} db_rc=${db_rc} $(date '+%Y-%m-%d %H:%M:%S %z')"
  exit "${db_rc}"
} >>"$LOG" 2>&1
