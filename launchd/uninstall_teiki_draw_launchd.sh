#!/bin/zsh
# uninstall: テイチャン自動抽選
set -euo pipefail
LABEL="com.matsunoma.jarvis.teiki-draw"
PLIST="${HOME}/Library/LaunchAgents/${LABEL}.plist"
launchctl bootout "gui/$(id -u)/${LABEL}" 2>/dev/null || true
rm -f "$PLIST"
echo "uninstalled ${LABEL}"
