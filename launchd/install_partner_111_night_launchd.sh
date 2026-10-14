#!/bin/zsh
# install: 111 夜枠（毎日 20:30 JST）
set -euo pipefail
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
LABEL="com.matsunoma.jarvis.partner-111-night"
PLIST="${HOME}/Library/LaunchAgents/${LABEL}.plist"
RUNNER="${REPO_DIR}/launchd/partner_111_night_runner.sh"
LOG_DIR="${HOME}/Library/Logs/jarvis_partner_111_night"
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
    <key>Hour</key>
    <integer>20</integer>
    <key>Minute</key>
    <integer>30</integer>
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
echo "installed ${LABEL} (daily 20:30 JST) → ${PLIST}"
echo "logs: ${LOG_DIR}/"
echo "manual: ${RUNNER}"
echo "dry: cd ${REPO_DIR} && python scripts/jarvis_partner_night_pipeline.py --force --skip-line --dry-run-slack"
