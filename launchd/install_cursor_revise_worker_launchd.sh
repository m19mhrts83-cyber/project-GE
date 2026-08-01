#!/bin/zsh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
LAUNCH_AGENTS_DIR="${HOME}/Library/LaunchAgents"
LOG_DIR="${HOME}/Library/Logs/jarvis_night_triage"
UID_VALUE="$(id -u)"
LABEL="com.matsunoma.jarvis.cursor-revise-worker"
PLIST="${LAUNCH_AGENTS_DIR}/${LABEL}.plist"

mkdir -p "$LAUNCH_AGENTS_DIR" "$LOG_DIR"
chmod +x "${SCRIPT_DIR}/cursor_revise_worker_runner.sh"

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
    <string>cd "${REPO_DIR}" &amp;&amp; "${REPO_DIR}/launchd/cursor_revise_worker_runner.sh"</string>
  </array>
  <key>WorkingDirectory</key>
  <string>${REPO_DIR}</string>
  <key>RunAtLoad</key>
  <true/>
  <key>StartInterval</key>
  <integer>45</integer>
  <key>StandardOutPath</key>
  <string>${LOG_DIR}/cursor_revise.out.log</string>
  <key>StandardErrorPath</key>
  <string>${LOG_DIR}/cursor_revise.err.log</string>
</dict>
</plist>
EOF

launchctl bootout "gui/${UID_VALUE}/${LABEL}" > /dev/null 2>&1 || true
sleep 1
launchctl enable "gui/${UID_VALUE}/${LABEL}" || true
launchctl bootstrap "gui/${UID_VALUE}" "$PLIST"

echo "Installed: ${LABEL}"
echo "Schedule: every 45s (queued Cursor Agent revise from dashboard)"
echo "Logs: ${LOG_DIR}/cursor_revise.*.log"
launchctl print "gui/${UID_VALUE}/${LABEL}" | /usr/bin/awk '/state =|last exit code|runs =/'
