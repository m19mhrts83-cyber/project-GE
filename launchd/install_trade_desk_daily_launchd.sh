#!/bin/zsh
# install: Trade Desk 日次（月〜金 16:45 JST）
set -euo pipefail
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
LABEL="com.matsunoma.jarvis.trade-desk-daily"
PLIST="${HOME}/Library/LaunchAgents/${LABEL}.plist"
RUNNER="${REPO_DIR}/launchd/trade_desk_daily_runner.sh"
LOG_DIR="${HOME}/Library/Logs/jarvis_trade_desk"
mkdir -p "$LOG_DIR"
chmod +x "$RUNNER"

INTERVALS=""
for wd in 1 2 3 4 5; do
  INTERVALS="${INTERVALS}
    <dict>
      <key>Weekday</key>
      <integer>${wd}</integer>
      <key>Hour</key>
      <integer>16</integer>
      <key>Minute</key>
      <integer>45</integer>
    </dict>"
done

cat >"$PLIST" <<EOF
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
  <array>${INTERVALS}
  </array>
  <key>RunAtLoad</key>
  <false/>
  <key>StandardOutPath</key>
  <string>${LOG_DIR}/launchd.out.log</string>
  <key>StandardErrorPath</key>
  <string>${LOG_DIR}/launchd.err.log</string>
</dict>
</plist>
EOF

launchctl bootout "gui/$(id -u)/${LABEL}" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST"
launchctl enable "gui/$(id -u)/${LABEL}"
echo "installed ${LABEL} (Mon-Fri 16:45) → ${PLIST}"
echo "logs: ${LOG_DIR}/"
