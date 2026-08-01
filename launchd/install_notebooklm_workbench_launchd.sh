#!/bin/zsh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
LAUNCH_AGENTS_DIR="${HOME}/Library/LaunchAgents"
LOG_DIR="${HOME}/Library/Logs/jarvis_notebooklm"
UID_VALUE="$(id -u)"
LABEL="com.matsunoma.jarvis.notebooklm-workbench"
PLIST="${LAUNCH_AGENTS_DIR}/${LABEL}.plist"

mkdir -p "$LAUNCH_AGENTS_DIR" "$LOG_DIR"
chmod +x "${SCRIPT_DIR}/notebooklm_workbench_runner.sh"
chmod +x "${REPO_DIR}/scripts/jarvis_notebooklm_workbench_open.py"
chmod +x "${REPO_DIR}/scripts/jarvis_notebooklm_workbench_helper.py"

# 既存プロセスを止めてから入れ替え
pkill -f 'jarvis_notebooklm_workbench_helper.py' 2>/dev/null || true
sleep 1

cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>${LABEL}</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/zsh</string>
    <string>-lc</string>
    <string>cd "${REPO_DIR}" &amp;&amp; "${REPO_DIR}/launchd/notebooklm_workbench_runner.sh"</string>
  </array>
  <key>WorkingDirectory</key>
  <string>${REPO_DIR}</string>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>
  <key>ThrottleInterval</key>
  <integer>5</integer>
  <key>StandardOutPath</key>
  <string>${LOG_DIR}/workbench.out.log</string>
  <key>StandardErrorPath</key>
  <string>${LOG_DIR}/workbench.err.log</string>
</dict>
</plist>
EOF

launchctl bootout "gui/${UID_VALUE}/${LABEL}" > /dev/null 2>&1 || true
sleep 1
launchctl enable "gui/${UID_VALUE}/${LABEL}" || true
launchctl bootstrap "gui/${UID_VALUE}" "$PLIST"
sleep 2
launchctl kickstart -k "gui/${UID_VALUE}/${LABEL}" || true

echo "Installed: ${LABEL} (KeepAlive)"
echo "URL: http://127.0.0.1:8766/notebooklm-workbench"
launchctl print "gui/${UID_VALUE}/${LABEL}" | /usr/bin/awk '/state =|pid =|last exit code/'
