#!/bin/zsh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
LOG_DIR="${HOME}/Library/Logs/line_open_chat"
ALERT_FILE="${LOG_DIR}/NEEDS_RELOGIN.txt"

mkdir -p "$LOG_DIR"

notify_relogin_needed() {
  local message="$1"
  if command -v osascript > /dev/null 2>&1; then
    /usr/bin/osascript -e "display notification \"${message}\" with title \"LINE Open Chat\" subtitle \"再ログイン確認が必要です\" sound name \"Glass\"" > /dev/null 2>&1 || true
  fi
}

alert_and_exit() {
  local message="$1"
  echo "$(date '+%Y-%m-%d %H:%M:%S') [health] ${message}" >> "$ALERT_FILE"
  notify_relogin_needed "${message}"
  exit 1
}

cd "$REPO_DIR"

if [[ -f ".env" ]]; then
  set -a
  source ".env"
  set +a
fi

if [[ ! -x "$REPO_DIR/run_patch.sh" ]]; then
  alert_and_exit "run_patch.sh が見つかりません"
fi

if [[ -z "${LINE_UNOFFICIAL_AUTH_DIR:-}" ]]; then
  LINE_UNOFFICIAL_AUTH_DIR="$REPO_DIR/.line_auth"
fi

if [[ ! -d "$LINE_UNOFFICIAL_AUTH_DIR/.tokens" ]]; then
  alert_and_exit "保存トークンが見つかりません: $LINE_UNOFFICIAL_AUTH_DIR/.tokens"
fi

# 常駐中に別クライアントでAPIを叩くとデスクトップ認証を傷めるため、
# 状態ハートビートとプロセス生存だけを確認する。
if /usr/bin/pgrep -f 'application\.jp\.naver\.line\.mac|/Applications/LINE\.app' > /dev/null 2>&1; then
  alert_and_exit "Mac版LINEが起動中です。監視との認証競合を避けるため終了してください"
fi

STATUS_FILE="$LINE_UNOFFICIAL_AUTH_DIR/.chrline_open_chat_watch_status.json"
if [[ ! -f "$STATUS_FILE" ]]; then
  alert_and_exit "監視状態ファイルがありません。launchd監視を再起動してください"
fi

now="$(date +%s)"
updated="$(/usr/bin/stat -f %m "$STATUS_FILE" 2>/dev/null || echo 0)"
age=$(( now - updated ))
if (( age > 180 )); then
  alert_and_exit "監視ハートビートが${age}秒停止しています。launchd状態を確認してください"
fi

if ! /usr/bin/pgrep -f 'chrline_open_chat_realtime_watch\.py' > /dev/null 2>&1; then
  alert_and_exit "リアルタイム監視プロセスが見つかりません"
fi

rm -f "$ALERT_FILE"
echo "$(date '+%Y-%m-%d %H:%M:%S') [health] OK" >> "${LOG_DIR}/healthcheck_history.log"
