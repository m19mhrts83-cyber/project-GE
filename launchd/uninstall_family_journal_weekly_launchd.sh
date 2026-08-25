#!/bin/zsh
set -euo pipefail
LABEL="com.matsunoma.jarvis.family-journal-weekly"
launchctl bootout "gui/$(id -u)/${LABEL}" 2>/dev/null || true
rm -f "${HOME}/Library/LaunchAgents/${LABEL}.plist"
echo "uninstalled ${LABEL}"
