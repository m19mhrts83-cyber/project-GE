#!/bin/zsh
# install: 家族会議・週次（FRIDAY / 715）
#   本番: 日曜 21:30（会議終了後。ページ複製は松野さんが事前に実施）
#   リトライ: 月曜 07:00（--retry。完了済みなら何もしない）
set -euo pipefail
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
LABEL="com.matsunoma.friday.family-meeting-weekly"
RETRY_LABEL="${LABEL}-retry"
PLIST="${HOME}/Library/LaunchAgents/${LABEL}.plist"
RETRY_PLIST="${HOME}/Library/LaunchAgents/${RETRY_LABEL}.plist"
RUNNER="${REPO_DIR}/launchd/friday_family_meeting_weekly_runner.sh"
LOG_DIR="${HOME}/Library/Logs/friday_family_meeting_weekly"
mkdir -p "$LOG_DIR" "${HOME}/Library/LaunchAgents"
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
    <integer>30</integer>
  </dict>
  <key>StandardOutPath</key>
  <string>${LOG_DIR}/launchd.out.log</string>
  <key>StandardErrorPath</key>
  <string>${LOG_DIR}/launchd.err.log</string>
</dict>
</plist>
EOF

cat >"$RETRY_PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>${RETRY_LABEL}</string>
  <key>ProgramArguments</key>
  <array>
    <string>${RUNNER}</string>
    <string>--retry</string>
  </array>
  <key>StartCalendarInterval</key>
  <dict>
    <key>Weekday</key>
    <integer>1</integer>
    <key>Hour</key>
    <integer>7</integer>
    <key>Minute</key>
    <integer>0</integer>
  </dict>
  <key>StandardOutPath</key>
  <string>${LOG_DIR}/launchd.retry.out.log</string>
  <key>StandardErrorPath</key>
  <string>${LOG_DIR}/launchd.retry.err.log</string>
</dict>
</plist>
EOF

for spec in "${LABEL}:${PLIST}" "${RETRY_LABEL}:${RETRY_PLIST}"; do
  label="${spec%%:*}"
  plist="${spec#*:}"
  launchctl bootout "gui/$(id -u)/${label}" 2>/dev/null || true
  launchctl bootstrap "gui/$(id -u)" "$plist"
  launchctl enable "gui/$(id -u)/${label}"
done

echo "installed ${LABEL} (Sun 21:30) → ${PLIST}"
echo "installed ${RETRY_LABEL} (Mon 07:00 --retry) → ${RETRY_PLIST}"
echo "logs: ${LOG_DIR}/"
echo "前提: 当日 (YYYY/MM/DD) の Notion ページを松野さんが前週複製で用意しておく"
