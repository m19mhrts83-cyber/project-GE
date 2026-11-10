#!/bin/zsh
# install: 資産週次（毎日 09:10 JST）＋ Mac 起動時に未実施なら走らせる
# 毎日起こすが、その ISO 週に収集済み（時間外スキップなし）ならスクリプト側が即スキップする。
# 2026-11-10: 日曜だけだと ISO 週（月曜始まり）の最終日で、実収集は月曜 5時台の朝取りこぼしに
# 寄っていた。5時台はあかつき・アクサ・ソニー・MF が時間外で、日中に取り直す枠が無かった。
# 9:00 ジャストはソニーお客さまWEBの開店混雑を避ける。バッチ内でもソニーは後半。
set -euo pipefail
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
LABEL="com.matsunoma.jarvis.portfolio-weekly"
PLIST="${HOME}/Library/LaunchAgents/${LABEL}.plist"
RUNNER="${REPO_DIR}/launchd/portfolio_weekly_runner.sh"
LOG_DIR="${HOME}/Library/Logs/jarvis_portfolio"
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
    <integer>9</integer>
    <key>Minute</key>
    <integer>10</integer>
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
echo "installed ${LABEL} (daily 09:10 + RunAtLoad) → ${PLIST}"
echo "logs: ${LOG_DIR}/"
echo "週次スクリプト自体が ISO 週の成功済みなら起動時はスキップします"
