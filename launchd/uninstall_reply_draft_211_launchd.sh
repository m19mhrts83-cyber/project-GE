#!/bin/zsh
set -euo pipefail
UID_VALUE="$(id -u)"
LABEL="com.matsunoma.jarvis.reply-draft-211"
PLIST="${HOME}/Library/LaunchAgents/${LABEL}.plist"
launchctl bootout "gui/${UID_VALUE}/${LABEL}" > /dev/null 2>&1 || true
rm -f "$PLIST"
echo "Uninstalled: ${LABEL}"
