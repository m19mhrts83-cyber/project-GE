#!/bin/zsh
# install: WeStudy HTML バックアップ（毎週 日曜 12:00）。Mac が寝ていた場合は次に起きたときに実行される
# 週次取込（GHA・日曜 08:00）とずらしている。止める: WESTUDY_HTML_BACKUP_DISABLE=1 または launchctl bootout
set -euo pipefail
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
LABEL="com.matsunoma.westudy.html-backup"
PLIST="${HOME}/Library/LaunchAgents/${LABEL}.plist"
RUNNER="${REPO_DIR}/launchd/westudy_html_backup_runner.sh"
LOG_DIR="${HOME}/Library/Logs/westudy_html_backup"
chmod +x "$RUNNER"
mkdir -p "$LOG_DIR"

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
  <string>${LOG_DIR}/launchd.out.log</string>
  <key>StandardErrorPath</key>
  <string>${LOG_DIR}/launchd.err.log</string>
</dict>
</plist>
PLIST_EOF

launchctl bootout "gui/$(id -u)/${LABEL}" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST"
launchctl enable "gui/$(id -u)/${LABEL}"
echo "installed ${LABEL}（毎週 日曜 12:00）→ ${PLIST}"
echo "今すぐ1回動かす: launchctl kickstart gui/$(id -u)/${LABEL}"
echo "ログ: ${LOG_DIR}/launchd.out.log"
