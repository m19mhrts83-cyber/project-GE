#!/bin/zsh
# install: WeStudy グルコン投稿 watch（KeepAlive・3s＋Realtime 即ドレイン）
set -euo pipefail
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
LABEL="com.matsunoma.jarvis.westudy-forum-post"
PLIST="${HOME}/Library/LaunchAgents/${LABEL}.plist"
RUNNER="${REPO_DIR}/launchd/westudy_forum_post_runner.sh"
LOG_DIR="${HOME}/Library/Logs/jarvis_glucon"
mkdir -p "$LOG_DIR"
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
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>
  <key>ThrottleInterval</key>
  <integer>5</integer>
  <key>StandardOutPath</key>
  <string>${LOG_DIR}/watch.out.log</string>
  <key>StandardErrorPath</key>
  <string>${LOG_DIR}/watch.err.log</string>
</dict>
</plist>
EOF

launchctl bootout "gui/$(id -u)/${LABEL}" 2>/dev/null || true
sleep 1
launchctl bootstrap "gui/$(id -u)" "$PLIST"
launchctl enable "gui/$(id -u)/${LABEL}"
launchctl kickstart -k "gui/$(id -u)/${LABEL}" 2>/dev/null || true
echo "installed ${LABEL} (KeepAlive watch・queued 即ドレイン) → ${PLIST}"
echo "logs: ${LOG_DIR}/watch.*.log"
echo "heartbeat: ${REPO_DIR}/.jarvis_state/westudy_forum_post_watch.json"
echo "手動キック: ~/selenium_env/venv/bin/python scripts/jarvis_westudy_forum_post_kick.py"
