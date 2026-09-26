#!/bin/zsh
# uninstall: 画面ロック解除キャッチアップ
set -euo pipefail
LABEL="com.matsunoma.jarvis.screen-unlock-catchup"
PLIST="${HOME}/Library/LaunchAgents/${LABEL}.plist"
launchctl bootout "gui/$(id -u)/${LABEL}" 2>/dev/null || true
rm -f "$PLIST"
echo "uninstalled ${LABEL}"
