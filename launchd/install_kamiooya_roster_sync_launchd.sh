#!/bin/zsh
# install: 神大家Q&A (3) 名簿の毎日取り込み（毎朝 6:00 JST ＋ Mac 起動・ログイン時に未実施なら1回）
# 専用 worktree（~/.jarvis_worktrees/kamiooya-roster、origin/main を追う）を作り、
# launchd はその中の runner を動かす。~/git-repos の main（未コミットの変更あり）は使わない。
set -euo pipefail
MAIN_REPO="${HOME}/git-repos"
WT="${HOME}/.jarvis_worktrees/kamiooya-roster"
LABEL="com.matsunoma.jarvis.kamiooya-roster-sync"
PLIST="${HOME}/Library/LaunchAgents/${LABEL}.plist"
LOG_DIR="${HOME}/Library/Logs/kamiooya_roster_sync"
mkdir -p "$LOG_DIR" "$(dirname "$WT")"

git -C "$MAIN_REPO" fetch -q origin main
if [[ ! -e "${WT}/.git" ]]; then
  git -C "$MAIN_REPO" worktree prune
  git -C "$MAIN_REPO" worktree add -q --detach "$WT" origin/main
else
  git -C "$WT" checkout -q -f --detach origin/main
fi
RUNNER="${WT}/launchd/kamiooya_roster_sync_runner.sh"
[[ -f "$RUNNER" ]] || { echo "runner が origin/main にありません（PR マージ後に実行してください）: $RUNNER" >&2; exit 1; }

cat >"$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>${LABEL}</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/zsh</string>
    <string>${RUNNER}</string>
  </array>
  <key>StartCalendarInterval</key>
  <dict>
    <key>Hour</key>
    <integer>6</integer>
    <key>Minute</key>
    <integer>0</integer>
  </dict>
  <key>RunAtLoad</key>
  <true/>
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
echo "installed ${LABEL}（毎朝 6:00 JST ＋ 起動時。その日成功済みならスキップ）→ ${PLIST}"
echo "worktree: ${WT}"
echo "logs: ${LOG_DIR}/sync.log"
