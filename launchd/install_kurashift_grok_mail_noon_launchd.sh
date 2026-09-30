#!/bin/zsh
# install: KURASHIFT Grok 調査メール 昼追撃（毎日 11:00 JST）
# 注意: 本番 Mac へのインストールはユーザー了承後。本 PR ではファイル追加のみ。
set -euo pipefail
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
LABEL="com.matsunoma.jarvis.kurashift-grok-mail-noon"
PLIST="${HOME}/Library/LaunchAgents/${LABEL}.plist"
RUNNER="${REPO_DIR}/launchd/kurashift_grok_mail_noon_runner.sh"
LOG_DIR="${HOME}/Library/Logs/jarvis_kurashift"
mkdir -p "$LOG_DIR"
chmod +x "$RUNNER"

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
  <dict>
    <key>Hour</key>
    <integer>11</integer>
    <key>Minute</key>
    <integer>0</integer>
  </dict>
  <key>StandardOutPath</key>
  <string>${LOG_DIR}/grok_mail_noon_launchd.out.log</string>
  <key>StandardErrorPath</key>
  <string>${LOG_DIR}/grok_mail_noon_launchd.err.log</string>
</dict>
</plist>
EOF

launchctl bootout "gui/$(id -u)/${LABEL}" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST"
launchctl enable "gui/$(id -u)/${LABEL}"
echo "installed ${LABEL} (毎日 11:00) → ${PLIST}"
echo "logs: ${LOG_DIR}/"
echo "本線は GHA kurashift-grok-mail-noon.yml も可（どちらか一方で足りる）"
