#!/bin/zsh
# install: 神大家 講座動画の週次取込（日曜 12:00。日曜 08:00 の GHA コメント取込の後）
set -euo pipefail
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
LABEL="com.matsunoma.jarvis.kamiooya-video-weekly"
PLIST="${HOME}/Library/LaunchAgents/${LABEL}.plist"
RUNNER="${REPO_DIR}/launchd/kamiooya_video_weekly_runner.sh"
chmod +x "$RUNNER"
mkdir -p "${HOME}/Library/Logs/kamiooya_video_weekly"

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
  <dict><key>Weekday</key><integer>0</integer><key>Hour</key><integer>12</integer><key>Minute</key><integer>0</integer></dict>
  <key>StandardOutPath</key>
  <string>${HOME}/Library/Logs/kamiooya_video_weekly/launchd.out.log</string>
  <key>StandardErrorPath</key>
  <string>${HOME}/Library/Logs/kamiooya_video_weekly/launchd.err.log</string>
</dict>
</plist>
PLIST_EOF

launchctl bootout "gui/$(id -u)/${LABEL}" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST"
launchctl enable "gui/$(id -u)/${LABEL}"
echo "installed ${LABEL} (日曜 12:00) → ${PLIST}"
echo "今すぐ1回: launchctl kickstart gui/$(id -u)/${LABEL}"
echo "stop: KAMIOOYA_VIDEO_WEEKLY_DISABLE=1 または launchctl bootout gui/$(id -u)/${LABEL}"
