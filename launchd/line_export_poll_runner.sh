#!/bin/zsh
# Jarvis: LINE 公式エクスポート定常取込（15分ポーリング）
#   EmailMe → Gmail(matsuno.estate) → inbox → 5.やり取り.md
#   = line_export_gmail_to_inbox.py → line_export_inbox_to_yoritoori.py
# 失敗しても止めない（soft-fail）。次回ポーリングで回収する。
# Mac版LINEは起動しない（CHRLINEと競合。jarvis-line-desktop-conflict.mdc）。
set -uo pipefail
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PY="${HOME}/selenium_env/venv/bin/python"
MANUAL_DIR="${REPO_DIR}/215_kamiooya/C1_cursor/1b_Cursorマニュアル"
LOG_DIR="${HOME}/Library/Logs/jarvis_line_export"
mkdir -p "$LOG_DIR"
STAMP="$(date +%Y%m%d_%H%M%S)"
LOG="${LOG_DIR}/poll_${STAMP}.log"
LOCK_DIR="${LOG_DIR}/poll.lock"

# 多重起動防止。stale lock（15分超）は回収する。
acquired=0
if mkdir "$LOCK_DIR" 2>/dev/null; then
  acquired=1
elif [[ -d "$LOCK_DIR" ]]; then
  age=$(( $(date +%s) - $(stat -f %m "$LOCK_DIR" 2>/dev/null || echo 0) ))
  if (( age > 900 )); then
    rm -rf "$LOCK_DIR"
    mkdir "$LOCK_DIR" 2>/dev/null && acquired=1
  fi
fi
(( acquired )) || exit 0
trap 'rm -rf "$LOCK_DIR"' EXIT

cd "$REPO_DIR"
# .env は壊れた行があっても落とさない（本読込は Python 側 load_private_env）
if [[ -f "${REPO_DIR}/.env.jarvis_private" ]]; then
  set -a
  source "${REPO_DIR}/.env.jarvis_private" 2>>"${LOG_DIR}/env_source.err.log"
  set +a
fi

cd "$MANUAL_DIR"
{
  echo "# start $(date '+%Y-%m-%d %H:%M:%S %z')"
  # LINE 公式アカウント Bot（Webhook受信分）→ 公式エクスポート形式の .txt を inbox へ
  "$PY" -u "${REPO_DIR}/scripts/jarvis_line_oa_pull.py" --all
  echo "# line_oa_pull exit=$?"
  "$PY" -u line_export_gmail_to_inbox.py
  echo "# gmail_to_inbox exit=$?"
  "$PY" -u line_export_inbox_to_yoritoori.py
  echo "# inbox_to_yoritoori exit=$?"
  echo "# end $(date '+%Y-%m-%d %H:%M:%S %z')"
} >>"$LOG" 2>&1

# ログ肥大化防止: 14日超を削除
find "$LOG_DIR" -name 'poll_*.log' -mtime +14 -delete 2>/dev/null || true
