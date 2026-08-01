#!/bin/zsh
set -euo pipefail

UID_VALUE="$(id -u)"
LABEL="com.matsunoma.jarvis.notebooklm-workbench"
PLIST="${HOME}/Library/LaunchAgents/${LABEL}.plist"

launchctl bootout "gui/${UID_VALUE}/${LABEL}" > /dev/null 2>&1 || true
pkill -f 'jarvis_notebooklm_workbench_helper.py' 2>/dev/null || true
rm -f "$PLIST"
echo "Uninstalled: ${LABEL}"
