#!/bin/zsh
# install: ETC 平日朝夕還元の月次自動取得（20〜26日 09:30 JST）
set -euo pipefail
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
LABEL="com.matsunoma.jarvis.etc-rebate-monthly"
PLIST="${HOME}/Library/LaunchAgents/${LABEL}.plist"
RUNNER="${REPO_DIR}/launchd/etc_rebate_monthly_runner.sh"
LOG_DIR="${HOME}/Library/Logs/jarvis_etc_rebate"
mkdir -p "$LOG_DIR"
chmod +x "$RUNNER"

# StartCalendarInterval を配列で 20〜26日
INTERVALS=""
for d in 20 21 22 23 24 25 26; do
  INTERVALS="${INTERVALS}
    <dict>
      <key>Day</key>
      <integer>${d}</integer>
      <key>Hour</key>
      <integer>9</integer>
      <key>Minute</key>
      <integer>30</integer>
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
echo "installed ${LABEL} (日 20–26 · 09:30 JST) → ${PLIST}"
echo "logs: ${LOG_DIR}/"
echo "手動: ${REPO_DIR}/scripts/jarvis_etc_rebate_fetch.py --apply --push"
echo "無効化: JARVIS_ETC_REBATE_AUTO_DISABLE=1 または etc_monthly.json disabled"
