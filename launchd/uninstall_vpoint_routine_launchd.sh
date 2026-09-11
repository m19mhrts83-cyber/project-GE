#!/bin/zsh
# uninstall: Vポイント定例
set -euo pipefail
LABEL="com.matsunoma.jarvis.vpoint-routine"
PLIST="${HOME}/Library/LaunchAgents/${LABEL}.plist"
launchctl bootout "gui/$(id -u)/${LABEL}" 2>/dev/null || true
rm -f "$PLIST"
echo "uninstalled ${LABEL}"
