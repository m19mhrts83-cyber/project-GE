#!/bin/zsh
# install: Jarvis repo → OneDrive 疎ミラー（日曜 09:15 JST・RunAtLoad なし）
#
# 秘密バックアップ（private-backup・日曜 08:30）と時刻をずらしてある。
set -euo pipefail
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
LABEL="com.matsunoma.jarvis.repo-mirror"
PLIST="${HOME}/Library/LaunchAgents/${LABEL}.plist"
RUNNER="${REPO_DIR}/launchd/jarvis_repo_mirror_runner.sh"
LOG_DIR="${HOME}/Library/Logs/jarvis_repo_mirror"
mkdir -p "$LOG_DIR"
chmod +x "$RUNNER"
chmod +x "${REPO_DIR}/scripts/jarvis_repo_onedrive_mirror.sh"

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
    <integer>9</integer>
    <key>Minute</key>
    <integer>15</integer>
  </dict>
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
echo "installed ${LABEL} (Sun 09:15 JST) → ${PLIST}"
echo "logs: ${LOG_DIR}/"
echo "手動実行: ${REPO_DIR}/scripts/jarvis_repo_onedrive_mirror.sh        # dry-run"
echo "          ${REPO_DIR}/scripts/jarvis_repo_onedrive_mirror.sh --apply # 本番"
