#!/bin/zsh
# uninstall: LINE 公式エクスポート定常取込
set -euo pipefail
LABEL="com.matsunoma.jarvis.line-export-poll"
PLIST="${HOME}/Library/LaunchAgents/${LABEL}.plist"
launchctl bootout "gui/$(id -u)/${LABEL}" 2>/dev/null || true
rm -f "$PLIST"
echo "uninstalled ${LABEL}"
