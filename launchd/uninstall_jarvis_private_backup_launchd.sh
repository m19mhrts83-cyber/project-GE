#!/bin/zsh
# uninstall: Jarvis Private 暗号化バックアップ
set -euo pipefail
LABEL="com.matsunoma.jarvis.private-backup"
PLIST="${HOME}/Library/LaunchAgents/${LABEL}.plist"
launchctl bootout "gui/$(id -u)/${LABEL}" 2>/dev/null || true
rm -f "$PLIST"
echo "uninstalled ${LABEL}"
