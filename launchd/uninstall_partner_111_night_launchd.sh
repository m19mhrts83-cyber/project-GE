#!/bin/zsh
set -euo pipefail
LABEL="com.matsunoma.jarvis.partner-111-night"
PLIST="${HOME}/Library/LaunchAgents/${LABEL}.plist"
launchctl bootout "gui/$(id -u)/${LABEL}" 2>/dev/null || true
rm -f "$PLIST"
echo "uninstalled ${LABEL}"
