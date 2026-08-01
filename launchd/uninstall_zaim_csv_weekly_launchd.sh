#!/bin/zsh
set -euo pipefail
LABEL="com.matsunoma.jarvis.zaim-csv-weekly"
PLIST="${HOME}/Library/LaunchAgents/${LABEL}.plist"
launchctl bootout "gui/$(id -u)/${LABEL}" 2>/dev/null || true
rm -f "$PLIST"
echo "uninstalled ${LABEL}"
