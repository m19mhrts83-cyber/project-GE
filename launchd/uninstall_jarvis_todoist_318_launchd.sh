#!/bin/bash
# 318 Todoist消化係 10:30 の登録を外す（戻し手順の 1 番目）。plist も消す。ログは残す。
set -euo pipefail
UID_VALUE="$(id -u)"
LABEL="com.matsunoma.jarvis.todoist-318"
PLIST="${HOME}/Library/LaunchAgents/${LABEL}.plist"
launchctl bootout "gui/${UID_VALUE}/${LABEL}" > /dev/null 2>&1 || true
rm -f "$PLIST"
echo "Removed: ${LABEL}（次は set-owner --who 313 --yes → 313 の予定タスクを戻す）"
