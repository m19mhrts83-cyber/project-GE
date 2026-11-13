#!/bin/zsh
# install: 定額AIの係（KeepAlive 常駐・3 秒ごとに ai_jobs を見る）
set -euo pipefail
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
LABEL="com.matsunoma.jarvis.flat-ai-worker"
PLIST="${HOME}/Library/LaunchAgents/${LABEL}.plist"
RUNNER="${REPO_DIR}/launchd/flat_ai_worker_runner.sh"
LOG_DIR="${HOME}/Library/Logs/jarvis_flat_ai"
mkdir -p "$LOG_DIR"
chmod +x "$RUNNER"

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
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>
  <key>ThrottleInterval</key>
  <integer>10</integer>
  <key>StandardOutPath</key>
  <string>${LOG_DIR}/worker.out.log</string>
  <key>StandardErrorPath</key>
  <string>${LOG_DIR}/worker.err.log</string>
</dict>
</plist>
PLIST_EOF

launchctl bootout "gui/$(id -u)/${LABEL}" 2>/dev/null || true
sleep 1
launchctl bootstrap "gui/$(id -u)" "$PLIST"
launchctl enable "gui/$(id -u)/${LABEL}"
launchctl kickstart -k "gui/$(id -u)/${LABEL}" 2>/dev/null || true
echo "installed ${LABEL} → ${PLIST}"
echo "logs: ${LOG_DIR}/worker.*.log"
