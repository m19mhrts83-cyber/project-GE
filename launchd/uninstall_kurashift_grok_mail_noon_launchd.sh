#!/bin/zsh
# uninstall: KURASHIFT Grok 調査メール 昼追撃
set -euo pipefail
LABEL="com.matsunoma.jarvis.kurashift-grok-mail-noon"
PLIST="${HOME}/Library/LaunchAgents/${LABEL}.plist"
launchctl bootout "gui/$(id -u)/${LABEL}" 2>/dev/null || true
rm -f "$PLIST"
echo "uninstalled ${LABEL}"
