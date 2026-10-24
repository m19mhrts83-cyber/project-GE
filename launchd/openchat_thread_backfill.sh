#!/bin/zsh
# 815 オプチャ: 新しくできたスレッドの追い上げ（手動・1回限りの回復用）
#
# 定常（朝夕の openchat_md_db_sync_runner.sh）は「前回以降にメインへ乗った新着スレッド通知」しか見ない。
# 長く止まっていた後（例: 2026-09-30〜10-24 は新スレッドが一切登録されていなかった）は、
# メインの履歴を深めに読んで（dry-run＝MD は触らない）新スレッドを集め、登録＋本文取得まで行う。
#
#   zsh launchd/openchat_thread_backfill.sh            # 既定: メイン 30 ページ分さかのぼる
#   PAGES=60 zsh launchd/openchat_thread_backfill.sh
set -uo pipefail
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
POC="${REPO_DIR}/line_unofficial_poc"
LOG_DIR="${HOME}/Library/Logs/jarvis_openchat_sync"
mkdir -p "$LOG_DIR"
LOG="${LOG_DIR}/backfill_$(date +%Y%m%d_%H%M%S).log"
PAGES="${PAGES:-30}"
ACTIVE_JSON="${POC}/.line_auth/active_thread_mids.json"

resume() { "${POC}/launchd/open_chat_watch_resume.sh" >>"$LOG" 2>&1 || true; }
trap resume EXIT INT TERM

if pgrep -f 'application\.jp\.naver\.line\.mac|/Applications/LINE\.app' >/dev/null 2>&1; then
  echo "abort: Mac版LINE 起動中（CHRLINE競合）" | tee -a "$LOG"
  exit 3
fi
if [[ -f "${REPO_DIR}/.env.jarvis_private" ]]; then
  set -a; source "${REPO_DIR}/.env.jarvis_private" 2>/dev/null; set +a
fi
"${POC}/launchd/open_chat_watch_pause.sh" >>"$LOG" 2>&1 || true

cd "$POC"
echo "# 1) メイン ${PAGES} ページ分の新スレッド通知を収集（dry-run）" | tee -a "$LOG"
./run_patch.sh chrline_open_chat_to_md.py --no-threads --dry-run --init \
  --max-pages-per-stream "$PAGES" --active-threads-out "$ACTIVE_JSON" >>"$LOG" 2>&1
echo "# 2) 新スレッドを登録して本文を取得" | tee -a "$LOG"
./run_patch.sh chrline_open_chat_to_md.py --threads-only --register-active-threads \
  --thread-mids-from "$ACTIVE_JSON" >>"$LOG" 2>&1
rc=$?
grep -E "^# (active threads|open_chat_routes|thread sync|open-chat 追記)" "$LOG" | tee /dev/stderr >/dev/null
echo "# done rc=${rc} log=${LOG}"
exit "$rc"
