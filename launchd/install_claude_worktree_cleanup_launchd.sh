#!/bin/zsh
# install: Claude Code ワークツリー片付け（毎週月曜 08:40）。2週間放置で中身が安全なものだけ消す
set -euo pipefail
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
LABEL="com.matsunoma.jarvis.claude-worktree-cleanup"
PLIST="${HOME}/Library/LaunchAgents/${LABEL}.plist"
RUNNER="${REPO_DIR}/scripts/jarvis_claude_worktree_cleanup.sh"
chmod +x "$RUNNER"
mkdir -p "${HOME}/Library/Logs/jarvis_claude_worktree_cleanup"

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
    <string>--apply</string>
  </array>
  <key>StartCalendarInterval</key>
  <dict><key>Weekday</key><integer>1</integer><key>Hour</key><integer>8</integer><key>Minute</key><integer>40</integer></dict>
  <key>StandardOutPath</key>
  <string>${HOME}/Library/Logs/jarvis_claude_worktree_cleanup/launchd.out.log</string>
  <key>StandardErrorPath</key>
  <string>${HOME}/Library/Logs/jarvis_claude_worktree_cleanup/launchd.err.log</string>
</dict>
</plist>
PLIST_EOF

launchctl bootout "gui/$(id -u)/${LABEL}" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST"
launchctl enable "gui/$(id -u)/${LABEL}"
echo "installed ${LABEL} (月曜 08:40) → ${PLIST}"
echo "stop: JARVIS_WORKTREE_CLEANUP_DISABLE=1 または launchctl bootout gui/$(id -u)/${LABEL}"
