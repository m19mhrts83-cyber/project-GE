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

if [[ ! -x "$REPO_DIR/.venv/bin/python" ]]; then
  alert_and_exit ".venv/bin/python が見つかりません"
fi

if [[ -z "${LINE_UNOFFICIAL_AUTH_DIR:-}" ]]; then
  LINE_UNOFFICIAL_AUTH_DIR="$REPO_DIR/.line_auth_local"
fi

if [[ ! -d "$LINE_UNOFFICIAL_AUTH_DIR/.tokens" ]]; then
  alert_and_exit "保存トークンが見つかりません: $LINE_UNOFFICIAL_AUTH_DIR/.tokens"
fi

if ! "$REPO_DIR/.venv/bin/python" "$REPO_DIR/chrline_list_open_chats_poc.py" --limit 1 > /dev/null 2>&1; then
  alert_and_exit "API チェック失敗。再ログイン推奨: $REPO_DIR/chrline_qr_login_poc.py"
fi

echo "$(date '+%Y-%m-%d %H:%M:%S') [health] OK" >> "${LOG_DIR}/healthcheck_history.log"
