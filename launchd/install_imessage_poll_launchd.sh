#!/bin/zsh
# install: iMessage 定常取込（20分ポーリング・要フルディスクアクセス）
set -euo pipefail
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
LABEL="com.matsunoma.jarvis.imessage-poll"
PLIST="${HOME}/Library/LaunchAgents/${LABEL}.plist"
RUNNER="${IMESSAGE_POLL_RUNNER:-${REPO_DIR}/launchd/imessage_poll_runner.sh}"  # 本番は ~/git-repos 側（main 反映後）
chmod +x "$RUNNER"
mkdir -p "${HOME}/Library/Logs/jarvis_imessage"

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
  <key>StartInterval</key>
  <integer>1200</integer>
  <key>RunAtLoad</key>
  <true/>
  <key>StandardOutPath</key>
  <string>${HOME}/Library/Logs/jarvis_imessage/launchd.out.log</string>
  <key>StandardErrorPath</key>
  <string>${HOME}/Library/Logs/jarvis_imessage/launchd.err.log</string>
</dict>
</plist>
EOF

launchctl bootout "gui/$(id -u)/${LABEL}" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST"
launchctl enable "gui/$(id -u)/${LABEL}"
echo "installed ${LABEL} (every 1200s) → ${PLIST}"
