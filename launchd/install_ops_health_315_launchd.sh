#!/bin/zsh
# install: 315 Mac補完 — 日曜 21:45 JST（GHA 21:00 のあと・--remediate-once）
set -euo pipefail
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
LABEL="com.matsunoma.jarvis.ops-health-315"
PLIST="${HOME}/Library/LaunchAgents/${LABEL}.plist"
RUNNER="${REPO_DIR}/launchd/ops_health_315_runner.sh"
LOG_DIR="${HOME}/Library/Logs/jarvis_ops_health_315"
mkdir -p "$LOG_DIR"
chmod +x "$RUNNER"

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
  <dict>
    <key>Weekday</key>
    <integer>0</integer>
    <key>Hour</key>
    <integer>21</integer>
    <key>Minute</key>
    <integer>45</integer>
  </dict>
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
echo "installed ${LABEL} (Sun 21:45 JST · remediate-once) → ${PLIST}"
echo "logs: ${LOG_DIR}/"
echo "manual: ${RUNNER}"
echo "disable: JARVIS_OPS_HEALTH_315_DISABLE=1"
