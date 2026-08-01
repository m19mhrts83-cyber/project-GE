#!/bin/zsh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
LAUNCH_AGENTS_DIR="${HOME}/Library/LaunchAgents"
LOG_DIR="${HOME}/Library/Logs/jarvis_night_triage"
UID_VALUE="$(id -u)"
LABEL="com.matsunoma.jarvis.triage-morning-open"
PLIST="${LAUNCH_AGENTS_DIR}/${LABEL}.plist"

mkdir -p "$LAUNCH_AGENTS_DIR" "$LOG_DIR"
chmod +x "${SCRIPT_DIR}/triage_morning_open_runner.sh"

# ログイン時 + 起床後も拾うため短周期ポーリング（1日1回オープンは Python 側で抑制）
# スリープ中はタイマーが止まり、Mac を開いたあとに最初の実行で表示される想定
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
    <string>cd "${REPO_DIR}" &amp;&amp; "${REPO_DIR}/launchd/triage_morning_open_runner.sh"</string>
  </array>
  <key>WorkingDirectory</key>
  <string>${REPO_DIR}</string>
  <key>RunAtLoad</key>
  <true/>
  <key>StartInterval</key>
  <integer>120</integer>
  <key>StandardOutPath</key>
  <string>${LOG_DIR}/morning_open.out.log</string>
  <key>StandardErrorPath</key>
  <string>${LOG_DIR}/morning_open.err.log</string>
</dict>
</plist>
EOF

launchctl bootout "gui/${UID_VALUE}/${LABEL}" > /dev/null 2>&1 || true
sleep 1
launchctl enable "gui/${UID_VALUE}/${LABEL}" || true
launchctl bootstrap "gui/${UID_VALUE}" "$PLIST"

echo "Installed: ${LABEL}"
echo "Triggers: RunAtLoad (login) + every 120s (sleep 中は停止 → 開いた後の最初で表示)"
echo "Logs: ${LOG_DIR}/morning_open.*.log"
launchctl print "gui/${UID_VALUE}/${LABEL}" | /usr/bin/awk '/state =|last exit code|runs =/'
