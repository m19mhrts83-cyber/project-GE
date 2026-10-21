#!/bin/zsh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
LAUNCH_AGENTS_DIR="${HOME}/Library/LaunchAgents"
LOG_DIR="${HOME}/Library/Logs/jarvis_todoist_313_digest"
UID_VALUE="$(id -u)"
LABEL="com.matsunoma.jarvis.todoist-313-digest"
PLIST="${LAUNCH_AGENTS_DIR}/${LABEL}.plist"

mkdir -p "$LAUNCH_AGENTS_DIR" "$LOG_DIR"
chmod +x "${SCRIPT_DIR}/jarvis_todoist_313_digest_runner.sh"

cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>${LABEL}</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/zsh</string>
    <string>-lc</string>
    <string>cd "${REPO_DIR}" &amp;&amp; "${REPO_DIR}/launchd/jarvis_todoist_313_digest_runner.sh"</string>
  </array>
  <key>WorkingDirectory</key>
  <string>${REPO_DIR}</string>
  <key>RunAtLoad</key>
  <false/>
  <key>StartCalendarInterval</key>
  <dict>
    <key>Hour</key>
    <integer>20</integer>
    <key>Minute</key>
    <integer>0</integer>
  </dict>
  <key>StandardOutPath</key>
  <string>${LOG_DIR}/todoist_313_digest.out.log</string>
  <key>StandardErrorPath</key>
  <string>${LOG_DIR}/todoist_313_digest.err.log</string>
</dict>
</plist>
EOF

launchctl bootout "gui/${UID_VALUE}/${LABEL}" > /dev/null 2>&1 || true
sleep 1
launchctl enable "gui/${UID_VALUE}/${LABEL}" || true
launchctl bootstrap "gui/${UID_VALUE}" "$PLIST"

echo "Installed: ${LABEL}"
echo "Schedule: every day 20:00 (local)"
echo "Logs: ${LOG_DIR}/"
launchctl print "gui/${UID_VALUE}/${LABEL}" | /usr/bin/awk '/state =|last exit code|runs =/'
