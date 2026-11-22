#!/bin/bash
# 318 Todoist消化係 毎朝 10:30 を launchd に登録する（移管手順の 3 番目。松野さんの了承後だけ）。
# 先に: (1) 313 の予定タスク todoist-daily-313 を止める (2) 朝枠の担当を 318 にする
#   python3 scripts/jarvis_todoist_morning_slot.py set-owner --who 318 --yes
# 使い方: bash launchd/install_jarvis_todoist_318_launchd.sh --yes
# 戻し: bash launchd/uninstall_jarvis_todoist_318_launchd.sh
set -euo pipefail

if [[ "${1:-}" != "--yes" ]]; then
  echo "登録しない: --yes が要る（移管手順 318_Todoist消化係/移管手順_10時30分.md を確かめてから）" >&2
  exit 2
fi

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
PY="${HOME}/selenium_env/venv/bin/python"
[[ -x "$PY" ]] || PY="python3"

OWNER="$("$PY" -c 'import sys; sys.path.insert(0, sys.argv[1] + "/scripts"); import jarvis_todoist_morning_slot as m; from pathlib import Path; print(m.get_owner(Path(sys.argv[1]) / ".jarvis_state"))' "$REPO_DIR" 2>/dev/null || echo "?")"
if [[ "$OWNER" != "318" ]]; then
  echo "登録しない: 朝枠の担当が 318 ではない（今: ${OWNER}）。313 の予定タスクを止めてから set-owner --who 318 --yes" >&2
  exit 3
fi

LAUNCH_AGENTS_DIR="${HOME}/Library/LaunchAgents"
LOG_DIR="${HOME}/Library/Logs/jarvis_todoist_318"
UID_VALUE="$(id -u)"
LABEL="com.matsunoma.jarvis.todoist-318"
PLIST="${LAUNCH_AGENTS_DIR}/${LABEL}.plist"

mkdir -p "$LAUNCH_AGENTS_DIR" "$LOG_DIR"
chmod +x "${SCRIPT_DIR}/jarvis_todoist_318_runner.sh"
sed -e "s#__REPO__#${REPO_DIR}#g" -e "s#__HOME__#${HOME}#g" \
  "${SCRIPT_DIR}/${LABEL}.plist.template" > "$PLIST"
plutil -lint "$PLIST"

launchctl bootout "gui/${UID_VALUE}/${LABEL}" > /dev/null 2>&1 || true
sleep 1
launchctl enable "gui/${UID_VALUE}/${LABEL}" || true
launchctl bootstrap "gui/${UID_VALUE}" "$PLIST"

echo "Installed: ${LABEL}（毎朝 10:30・repo=${REPO_DIR}）"
echo "Logs: ${LOG_DIR}/"
launchctl print "gui/${UID_VALUE}/${LABEL}" | /usr/bin/awk '/state =|last exit code|runs =/'
