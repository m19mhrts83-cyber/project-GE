#!/bin/zsh
# install: Zaim CSV 土曜 05:00 JST 週次エクスポート（夜間トリアージと同刻）
set -euo pipefail
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
LABEL="com.matsunoma.jarvis.zaim-csv-weekly"
PLIST="${HOME}/Library/LaunchAgents/${LABEL}.plist"
RUNNER="${REPO_DIR}/launchd/zaim_csv_weekly_runner.sh"
LOG_DIR="${HOME}/Library/Logs/jarvis_zaim"
mkdir -p "$LOG_DIR"
chmod +x "$RUNNER"

# Apple Weekday: 0=Sun … 6=Sat
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
    <integer>6</integer>
    <key>Hour</key>
    <integer>5</integer>
    <key>Minute</key>
    <integer>0</integer>
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
echo "installed ${LABEL} (Saturday 05:00 JST) → ${PLIST}"
echo "manual: ${RUNNER}"
echo "fallback: Mac 朝オープン時に 6 日以上古い／未成功なら裏実行"
echo "logs: ${LOG_DIR}/"
