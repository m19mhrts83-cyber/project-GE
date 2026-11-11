#!/bin/zsh
# install: 神大家 講座動画の取込（毎日 12:00。08:00 の GHA コメント・レッスン取込の後）
# 日曜は従来の週次（全部）、月〜土は新着レッスンがあるときだけ取り込む（kamiooya_video_weekly.py --mode auto）
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
  <dict><key>Hour</key><integer>12</integer><key>Minute</key><integer>0</integer></dict>
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
echo "installed ${LABEL} (毎日 12:00。日曜は週次フル・平日は新着だけ) → ${PLIST}"
echo "今すぐ1回: launchctl kickstart gui/$(id -u)/${LABEL}"
echo "stop: KAMIOOYA_VIDEO_WEEKLY_DISABLE=1 または launchctl bootout gui/$(id -u)/${LABEL}"
