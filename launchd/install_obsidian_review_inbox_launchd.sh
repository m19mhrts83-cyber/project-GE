#!/bin/zsh
# Install ChatGPT review and read polling (every minute, Mac outbound-only).
set -euo pipefail
MODE_ARG=""
if [[ $# -eq 1 && "$1" == "--reads-only" ]]; then
  MODE_ARG="<string>--reads-only</string>"
elif [[ $# -ne 0 ]]; then
  echo "usage: $0 [--reads-only]" >&2
  exit 2
fi
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
LABEL="com.matsunoma.jarvis.obsidian-review-inbox"
PLIST="${HOME}/Library/LaunchAgents/${LABEL}.plist"
RUNNER="${REPO_DIR}/launchd/obsidian_review_inbox_runner.sh"
chmod +x "$RUNNER"
mkdir -p "${HOME}/Library/Logs/jarvis_obsidian_review" "${HOME}/Library/LaunchAgents"

cat >"$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>${LABEL}</string>
  <key>ProgramArguments</key>
  <array><string>${RUNNER}</string>${MODE_ARG}</array>
  <key>StartInterval</key><integer>60</integer>
  <key>RunAtLoad</key><true/>
  <key>StandardOutPath</key><string>${HOME}/Library/Logs/jarvis_obsidian_review/launchd.out.log</string>
  <key>StandardErrorPath</key><string>${HOME}/Library/Logs/jarvis_obsidian_review/launchd.err.log</string>
</dict>
</plist>
EOF

launchctl bootout "gui/$(id -u)/${LABEL}" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST"
launchctl enable "gui/$(id -u)/${LABEL}"
echo "installed ${LABEL} (every 60s) → ${PLIST}"
