#!/bin/zsh
set -euo pipefail

UID_VALUE="$(id -u)"
LAUNCH_AGENTS_DIR="${HOME}/Library/LaunchAgents"

WATCH_LABEL="com.matsunoma.line.openchat.watch"
HEALTH_LABEL="com.matsunoma.line.openchat.healthcheck"
WATCH_PLIST="${LAUNCH_AGENTS_DIR}/${WATCH_LABEL}.plist"
HEALTH_PLIST="${LAUNCH_AGENTS_DIR}/${HEALTH_LABEL}.plist"

launchctl bootout "gui/${UID_VALUE}" "$WATCH_PLIST" > /dev/null 2>&1 || true
launchctl bootout "gui/${UID_VALUE}" "$HEALTH_PLIST" > /dev/null 2>&1 || true

rm -f "$WATCH_PLIST" "$HEALTH_PLIST"

echo "Uninstalled launch agents:"
echo "  - ${WATCH_LABEL}"
echo "  - ${HEALTH_LABEL}"
