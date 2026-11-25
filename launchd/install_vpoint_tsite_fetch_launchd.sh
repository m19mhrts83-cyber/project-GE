#!/bin/zsh
# install: Vポイント Tサイト履歴の定期取得（毎月24日 08:30 JST）
set -euo pipefail
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
LABEL="com.matsunoma.jarvis.vpoint-tsite-fetch"
PLIST="${HOME}/Library/LaunchAgents/${LABEL}.plist"
RUNNER="${REPO_DIR}/launchd/vpoint_tsite_fetch_runner.sh"
LOG_DIR="${HOME}/Library/Logs/jarvis_vpoint_tsite_fetch"
mkdir -p "$LOG_DIR"
chmod +x "$RUNNER"

cat >"$PLIST" <<PLISTEOF
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
    <key>Day</key>
    <integer>24</integer>
    <key>Hour</key>
    <integer>8</integer>
    <key>Minute</key>
    <integer>30</integer>
  </dict>
  <key>StandardOutPath</key>
  <string>${LOG_DIR}/launchd.out.log</string>
  <key>StandardErrorPath</key>
  <string>${LOG_DIR}/launchd.err.log</string>
</dict>
</plist>
PLISTEOF

launchctl bootout "gui/$(id -u)/${LABEL}" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST"
launchctl enable "gui/$(id -u)/${LABEL}"
echo "installed ${LABEL} (毎月24日 08:30 JST) → ${PLIST}"
echo "logs: ${LOG_DIR}/"
echo "手動: ${REPO_DIR}/scripts/jarvis_vpoint_tsite_scheduled.py（--dry-run で予定だけ）"
echo "無効化: JARVIS_VPOINT_TSITE_FETCH_DISABLE=1（.env.jarvis_private）または uninstall_vpoint_tsite_fetch_launchd.sh"
