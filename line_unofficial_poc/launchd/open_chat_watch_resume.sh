#!/bin/zsh
# バッチ完了後に常駐監視を再開する。
set -euo pipefail
UID_VALUE="$(id -u)"
LABEL="com.matsunoma.line.openchat.watch"
PLIST="${HOME}/Library/LaunchAgents/${LABEL}.plist"
if [[ ! -f "$PLIST" ]]; then
  echo "[watch] plist がありません。先に ./launchd/install_open_chat_launchd.sh を実行してください。" >&2
  exit 1
fi
launchctl enable "gui/${UID_VALUE}/${LABEL}" > /dev/null 2>&1 || true
launchctl bootstrap "gui/${UID_VALUE}" "$PLIST" > /dev/null 2>&1 || true
launchctl kickstart -k "gui/${UID_VALUE}/${LABEL}" || true
echo "[watch] resumed: ${LABEL}"
