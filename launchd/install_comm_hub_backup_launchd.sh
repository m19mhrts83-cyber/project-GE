#!/bin/zsh
# コミュニケーション台帳の機械の予備を登録（毎日 13:40 と 21:10 JST）。マージ後に Mac で1回だけ実行。
set -euo pipefail
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
LABEL="com.matsunoma.jarvis.comm-hub-backup"
PLIST="${HOME}/Library/LaunchAgents/${LABEL}.plist"
RUNNER="${REPO_DIR}/launchd/comm_hub_backup_runner.sh"
chmod +x "$RUNNER"
mkdir -p "${HOME}/Library/Logs/jarvis_comm_hub_backup" "${HOME}/Library/LaunchAgents"

cat >"$PLIST" <<PL
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>${LABEL}</string>
  <key>ProgramArguments</key>
  <array><string>${RUNNER}</string></array>
  <key>StartCalendarInterval</key>
  <array>
    <dict><key>Hour</key><integer>13</integer><key>Minute</key><integer>40</integer></dict>
    <dict><key>Hour</key><integer>21</integer><key>Minute</key><integer>10</integer></dict>
  </array>
  <key>StandardOutPath</key><string>${HOME}/Library/Logs/jarvis_comm_hub_backup/launchd.out.log</string>
  <key>StandardErrorPath</key><string>${HOME}/Library/Logs/jarvis_comm_hub_backup/launchd.err.log</string>
</dict>
</plist>
PL

launchctl bootout "gui/$(id -u)/${LABEL}" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST"
launchctl enable "gui/$(id -u)/${LABEL}"
echo "installed ${LABEL} (13:40 / 21:10) → ${PLIST}"
