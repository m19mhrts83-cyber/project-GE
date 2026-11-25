#!/bin/zsh
# uninstall: Vポイント Tサイト履歴の定期取得
set -euo pipefail
LABEL="com.matsunoma.jarvis.vpoint-tsite-fetch"
PLIST="${HOME}/Library/LaunchAgents/${LABEL}.plist"
launchctl bootout "gui/$(id -u)/${LABEL}" 2>/dev/null || true
rm -f "$PLIST"
echo "uninstalled ${LABEL}"
