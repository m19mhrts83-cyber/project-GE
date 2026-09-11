#!/bin/zsh
# install: Vポイント定例（毎月 25〜月末 09:40 JST）
set -euo pipefail
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
LABEL="com.matsunoma.jarvis.vpoint-routine"
PLIST="${HOME}/Library/LaunchAgents/${LABEL}.plist"
RUNNER="${REPO_DIR}/launchd/vpoint_routine_runner.sh"
LOG_DIR="${HOME}/Library/Logs/jarvis_vpoint_routine"
mkdir -p "$LOG_DIR"
chmod +x "$RUNNER"

# 25〜31日（短い月は launchd が無視）
INTERVALS=""
for d in 25 26 27 28 29 30 31; do
  INTERVALS="${INTERVALS}
    <dict>
      <key>Day</key>
      <integer>${d}</integer>
      <key>Hour</key>
      <integer>9</integer>
      <key>Minute</key>
      <integer>40</integer>
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
echo "installed ${LABEL} (日 25–31 · 09:40 JST) → ${PLIST}"
echo "logs: ${LOG_DIR}/"
echo "手動: ${REPO_DIR}/scripts/jarvis_vpoint_routine.py --apply --push"
echo "窓外で付与も: … --force-window-c --apply --push"
echo "無効化: JARVIS_VPOINT_ROUTINE_DISABLE=1 または vpoint_monthly.json disabled"
