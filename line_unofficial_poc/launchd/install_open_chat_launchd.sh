#!/bin/zsh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
LAUNCH_AGENTS_DIR="${HOME}/Library/LaunchAgents"
LOG_DIR="${HOME}/Library/Logs/line_open_chat"
UID_VALUE="$(id -u)"

WATCH_LABEL="com.matsunoma.line.openchat.watch"
HEALTH_LABEL="com.matsunoma.line.openchat.healthcheck"
WATCH_PLIST="${LAUNCH_AGENTS_DIR}/${WATCH_LABEL}.plist"
HEALTH_PLIST="${LAUNCH_AGENTS_DIR}/${HEALTH_LABEL}.plist"

mkdir -p "$LAUNCH_AGENTS_DIR" "$LOG_DIR"

cat > "$WATCH_PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>${WATCH_LABEL}</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/zsh</string>
    <string>-lc</string>
    <string>cd "${REPO_DIR}" &amp;&amp; "${REPO_DIR}/launchd/open_chat_watch_runner.sh"</string>
  </array>
  <key>WorkingDirectory</key>
  <string>${REPO_DIR}</string>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>
  <key>ThrottleInterval</key>
  <integer>15</integer>
  <key>StandardOutPath</key>
  <string>${LOG_DIR}/watch.out.log</string>
  <key>StandardErrorPath</key>
  <string>${LOG_DIR}/watch.err.log</string>
</dict>
</plist>
EOF

cat > "$HEALTH_PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>${HEALTH_LABEL}</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/zsh</string>
    <string>-lc</string>
    <string>cd "${REPO_DIR}" &amp;&amp; "${REPO_DIR}/launchd/open_chat_healthcheck_runner.sh"</string>
  </array>
  <key>WorkingDirectory</key>
  <string>${REPO_DIR}</string>
  <key>RunAtLoad</key>
  <true/>
  <key>StartCalendarInterval</key>
  <dict>
    <key>Hour</key>
    <integer>4</integer>
    <key>Minute</key>
    <integer>10</integer>
  </dict>
  <key>StandardOutPath</key>
  <string>${LOG_DIR}/healthcheck.out.log</string>
  <key>StandardErrorPath</key>
  <string>${LOG_DIR}/healthcheck.err.log</string>
</dict>
</plist>
EOF

launchctl bootout "gui/${UID_VALUE}" "$WATCH_PLIST" > /dev/null 2>&1 || true
launchctl bootout "gui/${UID_VALUE}" "$HEALTH_PLIST" > /dev/null 2>&1 || true

launchctl bootstrap "gui/${UID_VALUE}" "$WATCH_PLIST"
launchctl bootstrap "gui/${UID_VALUE}" "$HEALTH_PLIST"

launchctl enable "gui/${UID_VALUE}/${WATCH_LABEL}" || true
launchctl enable "gui/${UID_VALUE}/${HEALTH_LABEL}" || true

launchctl kickstart -k "gui/${UID_VALUE}/${WATCH_LABEL}" || true
launchctl kickstart -k "gui/${UID_VALUE}/${HEALTH_LABEL}" || true

echo "Installed launch agents:"
echo "  - ${WATCH_LABEL}"
echo "  - ${HEALTH_LABEL}"
echo
echo "Status:"
launchctl print "gui/${UID_VALUE}/${WATCH_LABEL}" | /usr/bin/awk '/state =|pid =|last exit code/'
launchctl print "gui/${UID_VALUE}/${HEALTH_LABEL}" | /usr/bin/awk '/state =|pid =|last exit code/'
