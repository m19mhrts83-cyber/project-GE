#!/bin/zsh
# install: 物件進行ゲート 114（毎日 11:15 JST・Grok昼取込の直後）
# Jarvis／Cursor 上限でも Mac だけで Bカードまで進める。
set -euo pipefail
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
LABEL="com.matsunoma.jarvis.property-gate-114"
PLIST="${HOME}/Library/LaunchAgents/${LABEL}.plist"
RUNNER="${REPO_DIR}/launchd/property_gate_114_runner.sh"
LOG_DIR="${HOME}/Library/Logs/jarvis_property_gate"
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
    <integer>11</integer>
    <key>Minute</key>
    <integer>15</integer>
  </dict>
  <key>StandardOutPath</key>
  <string>${LOG_DIR}/gate114_launchd.out.log</string>
  <key>StandardErrorPath</key>
  <string>${LOG_DIR}/gate114_launchd.err.log</string>
</dict>
</plist>
EOF

launchctl bootout "gui/$(id -u)/${LABEL}" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST"
launchctl enable "gui/$(id -u)/${LABEL}"
echo "installed ${LABEL} (毎日 11:15) → ${PLIST}"
echo "logs: ${LOG_DIR}/"
echo "手動: ${RUNNER}"
echo "無効: JARVIS_PROPERTY_GATE_DISABLE=1"
