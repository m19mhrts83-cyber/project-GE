#!/bin/zsh
# install: OneDrive 書込の refresh_token を GHA Secrets へ同期（1時間ごと）
set -euo pipefail
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
LABEL="com.matsunoma.jarvis.ms-graph-refresh-gha-sync"
PLIST="${HOME}/Library/LaunchAgents/${LABEL}.plist"
RUNNER="${REPO_DIR}/launchd/ms_graph_refresh_gha_sync_runner.sh"
chmod +x "$RUNNER"
mkdir -p "${HOME}/Library/Logs/jarvis_ms_graph_sync"

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
  <integer>3600</integer>
  <key>RunAtLoad</key>
  <false/>
  <key>StandardOutPath</key>
  <string>${HOME}/Library/Logs/jarvis_ms_graph_sync/launchd.out.log</string>
  <key>StandardErrorPath</key>
  <string>${HOME}/Library/Logs/jarvis_ms_graph_sync/launchd.err.log</string>
</dict>
</plist>
EOF

launchctl bootout "gui/$(id -u)/${LABEL}" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST"
launchctl enable "gui/$(id -u)/${LABEL}"
echo "installed ${LABEL} (every 3600s) → ${PLIST}"
