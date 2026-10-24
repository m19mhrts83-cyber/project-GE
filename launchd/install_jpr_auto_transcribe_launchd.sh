#!/bin/zsh
# install: Just Press Record 自動文字起こし（1時間ごと）
set -euo pipefail
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
LABEL="com.matsunoma.jarvis.jpr-auto-transcribe"
PLIST="${HOME}/Library/LaunchAgents/${LABEL}.plist"
RUNNER="${REPO_DIR}/launchd/jpr_auto_transcribe_runner.sh"
chmod +x "$RUNNER"
mkdir -p "${HOME}/Library/Logs/jarvis_jpr_auto_transcribe"

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
  <key>StartInterval</key>
  <integer>3600</integer>
  <key>StandardOutPath</key>
  <string>${HOME}/Library/Logs/jarvis_jpr_auto_transcribe/launchd.out.log</string>
  <key>StandardErrorPath</key>
  <string>${HOME}/Library/Logs/jarvis_jpr_auto_transcribe/launchd.err.log</string>
</dict>
</plist>
PLIST_EOF

launchctl bootout "gui/$(id -u)/${LABEL}" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST"
launchctl enable "gui/$(id -u)/${LABEL}"
echo "installed ${LABEL} (hourly) → ${PLIST}"
echo "stop: launchctl bootout gui/$(id -u)/${LABEL}"
