#!/bin/zsh
# Jarvis: Todoist コメント入口（メール本線＋API保険）15分ポーリング
# 既定は報告のみ（--mark-read しない）。未読があるときだけログに残す。
# 自動既読化: JARVIS_TODOIST_COMMENT_INBOX_MARK_READ=1
set -euo pipefail
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PY="${HOME}/selenium_env/venv/bin/python"
LOG_DIR="${HOME}/Library/Logs/jarvis_todoist_comment"
mkdir -p "$LOG_DIR"
STAMP="$(date +%Y%m%d_%H%M%S)"
LOG="${LOG_DIR}/inbox_${STAMP}.log"

cd "$REPO_DIR"
if [[ -f "${REPO_DIR}/.env.jarvis_private" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "${REPO_DIR}/.env.jarvis_private"
  set +a
fi

ARGS=()
if [[ "${JARVIS_TODOIST_COMMENT_INBOX_MARK_READ:-0}" == "1" ]]; then
  ARGS+=(--mark-read)
fi

{
  echo "# start $(date '+%Y-%m-%d %H:%M:%S %z')"
  # 空配列の "${ARGS[@]+"${ARGS[@]}"}" は zsh が空文字を1引数として渡す（argparse が失敗する）。
  # 要素があるときだけ @ を展開する（set -u でも空の添字を参照しない）。
  if (( ${#ARGS[@]} )); then
    OUT="$("$PY" "${REPO_DIR}/scripts/jarvis_todoist_comment_inbox.py" "${ARGS[@]}" 2>&1)" || true
  else
    OUT="$("$PY" "${REPO_DIR}/scripts/jarvis_todoist_comment_inbox.py" 2>&1)" || true
  fi
  echo "$OUT"
  # 新規なしのときは短いログだけ残す（肥大化防止）
  if echo "$OUT" | grep -q '新規なし'; then
    :
  fi
  echo "# end"
} >>"$LOG" 2>&1

find "$LOG_DIR" -name 'inbox_*.log' -mtime +14 -delete 2>/dev/null || true
