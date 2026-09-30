#!/bin/zsh
# install: テイチャン自動抽選（月・木 10:15 JST）
set -euo pipefail
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
LABEL="com.matsunoma.jarvis.teiki-draw"
PLIST="${HOME}/Library/LaunchAgents/${LABEL}.plist"
RUNNER="${REPO_DIR}/launchd/teiki_draw_runner.sh"
LOG_DIR="${HOME}/Library/Logs/jarvis_teiki"
mkdir -p "$LOG_DIR"
chmod +x "$RUNNER"

# Weekday: 1=Mon … 4=Thu（Apple launchd）
INTERVALS=""
for w in 1 4; do
  INTERVALS="${INTERVALS}
    <dict>
      <key>Weekday</key>
      <integer>${w}</integer>
      <key>Hour</key>
      <integer>10</integer>
      <key>Minute</key>
      <integer>15</integer>
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
echo "installed ${LABEL} (月・木 10:15 JST) → ${PLIST}"
echo "logs: ${LOG_DIR}/"
echo "手動: ${REPO_DIR}/scripts/jarvis_teiki_barai_chance.py --run --push"
echo "無効化: JARVIS_TEIKI_BARAI_DISABLE=1 または teiki_barai_chance.json disabled"
