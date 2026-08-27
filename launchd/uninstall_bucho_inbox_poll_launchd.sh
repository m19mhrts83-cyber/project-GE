#!/bin/zsh
# uninstall: 部長ボックス inbox ポーリング
set -euo pipefail
LABEL="com.matsunoma.jarvis.bucho-inbox-poll"
PLIST="${HOME}/Library/LaunchAgents/${LABEL}.plist"
launchctl bootout "gui/$(id -u)/${LABEL}" 2>/dev/null || true
rm -f "$PLIST"
echo "uninstalled ${LABEL}"
