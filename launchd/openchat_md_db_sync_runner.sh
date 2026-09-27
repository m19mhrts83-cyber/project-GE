#!/bin/zsh
# 815 オプチャ: MD差分取込 → kamiooya-qa DB → ダッシュボード投影
# CHRLINE / OneDrive 正本必須 → launchd（Mac）本線
# set -e は使わない: 途中失敗でも必ず常時監視を resume するため rc を握る
set -uo pipefail
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
POC="${REPO_DIR}/line_unofficial_poc"
PY="${HOME}/selenium_env/venv/bin/python"
LOG_DIR="${HOME}/Library/Logs/jarvis_openchat_sync"
mkdir -p "$LOG_DIR"
STAMP="$(date +%Y%m%d_%H%M%S)"
LOG="${LOG_DIR}/sync_${STAMP}.log"
PAUSE="${POC}/launchd/open_chat_watch_pause.sh"
RESUME="${POC}/launchd/open_chat_watch_resume.sh"

# 監視を pause したら、成功・失敗を問わず必ず戻す（静かな停止の再発防止）
watch_paused=0
resume_watch() {
  if [[ "$watch_paused" -eq 1 && -x "$RESUME" ]]; then
    "$RESUME" >>"$LOG" 2>&1 || true
    echo "# [watch] resumed (trap) at $(date '+%Y-%m-%d %H:%M:%S %z')" >>"$LOG"
    watch_paused=0
  fi
}
trap resume_watch EXIT
trap 'resume_watch; exit 130' INT TERM

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
    watch_paused=1
  fi

  # メイン差分（スレは常時監視が本線。ここでは軽量にメイン中心）
  md_rc=0
  ( cd "$POC" && ./run_patch.sh chrline_open_chat_to_md.py --no-threads ) || md_rc=$?

  # MD → kamiooya-qa.line_openchat_logs（staging）＋ Grok共有
  # 二次投影の失敗で本線（取込・監視）を止めない
  db_rc=0
  "$PY" "${REPO_DIR}/scripts/jarvis_kurashift_openchat_sync.py" --apply --export-grok || db_rc=$?

  # staging → ready / excluded（ノイズのみ除外・検索公開）
  "$PY" "${REPO_DIR}/scripts/jarvis_openchat_publish.py" --apply || true

  # ダッシュボード /openchat（digest + thread health）
  "$PY" "${REPO_DIR}/scripts/jarvis_openchat_digest.py" --push || true
  "$PY" "${REPO_DIR}/scripts/jarvis_openchat_thread_health.py" --push || true

  resume_watch

  echo "# end md_rc=${md_rc} db_rc=${db_rc} $(date '+%Y-%m-%d %H:%M:%S %z')"
  exit "${md_rc}"
} >>"$LOG" 2>&1
