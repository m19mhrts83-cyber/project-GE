#!/bin/zsh
set -euo pipefail
UID_VALUE="$(id -u)"
LABEL="com.matsunoma.jarvis.night-triage"
PLIST="${HOME}/Library/LaunchAgents/${LABEL}.plist"
launchctl bootout "gui/${UID_VALUE}/${LABEL}" > /dev/null 2>&1 || true
rm -f "$PLIST"
echo "Uninstalled: ${LABEL}"
