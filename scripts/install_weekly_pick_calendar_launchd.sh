#!/bin/zsh
# install: 今週の9件のカレンダー取込（日曜 16:30 と毎朝 6:30）
set -euo pipefail
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
LABEL="com.matsunoma.jarvis.weekly-pick-calendar"
PLIST="${HOME}/Library/LaunchAgents/${LABEL}.plist"
RUNNER="${REPO_DIR}/launchd/weekly_pick_calendar_runner.sh"
chmod +x "$RUNNER"
mkdir -p "${HOME}/Library/Logs/weekly_pick_calendar"

cat >"$PLIST" <<PLIST_EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>${LABEL}</string>
  <key>ProgramArguments</key>
  <array>
    <string>${RUNNER}</string>
  </array>
  <key>StartCalendarInterval</key>
  <array>
    <dict><key>Weekday</key><integer>0</integer><key>Hour</key><integer>16</integer><key>Minute</key><integer>30</integer></dict>
    <dict><key>Hour</key><integer>6</integer><key>Minute</key><integer>30</integer></dict>
  </array>
  <key>StandardOutPath</key>
  <string>${HOME}/Library/Logs/weekly_pick_calendar/launchd.out.log</string>
  <key>StandardErrorPath</key>
  <string>${HOME}/Library/Logs/weekly_pick_calendar/launchd.err.log</string>
</dict>
</plist>
PLIST_EOF

launchctl bootout "gui/$(id -u)/${LABEL}" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST"
launchctl enable "gui/$(id -u)/${LABEL}"
echo "installed ${LABEL}（日曜 16:30・毎朝 6:30）→ ${PLIST}"
echo "今すぐ1回: launchctl kickstart gui/$(id -u)/${LABEL}"
