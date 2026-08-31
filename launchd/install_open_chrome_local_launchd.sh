#!/bin/bash
# Mac: KURASHIFT 掲載ページを Google Chrome で開くローカルヘルパーを launchd 登録
set -euo pipefail
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
LABEL="com.matsunoma.jarvis.open-chrome-local"
PLIST="$HOME/Library/LaunchAgents/${LABEL}.plist"
PY="${PY:-/Users/matsunomasaharu2/selenium_env/venv/bin/python}"
LOG_DIR="${HOME}/Library/Logs/jarvis_open_chrome"
mkdir -p "$LOG_DIR"

launchctl bootout "gui/$(id -u)/${LABEL}" 2>/dev/null || true
pkill -f 'jarvis_open_chrome_local.py' 2>/dev/null || true

cat >"$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>${LABEL}</string>
  <key>ProgramArguments</key>
  <array>
    <string>${PY}</string>
    <string>-u</string>
    <string>${REPO_DIR}/scripts/jarvis_open_chrome_local.py</string>
  </array>
  <key>WorkingDirectory</key>
  <string>${REPO_DIR}</string>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>
  <key>StandardOutPath</key>
  <string>${LOG_DIR}/out.log</string>
  <key>StandardErrorPath</key>
  <string>${LOG_DIR}/err.log</string>
</dict>
</plist>
EOF

launchctl bootstrap "gui/$(id -u)" "$PLIST"
sleep 1
curl -fsS "http://127.0.0.1:18765/health" && echo ""
echo "installed: ${LABEL}"
echo "endpoint: http://127.0.0.1:18765/open-chrome?url=..."
