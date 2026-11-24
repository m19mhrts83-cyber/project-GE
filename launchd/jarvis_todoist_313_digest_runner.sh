#!/bin/zsh
# Todoistタスク処置（313）— 金曜 20:00 週の整理 runner
# 旧: 毎晩 20:00 片付け3択（2026-11-24 で停止。手動なら引数付きで cleanup.py を呼べる）
set -euo pipefail
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PY="${HOME}/selenium_env/venv/bin/python"
LOG_DIR="${HOME}/Library/Logs/jarvis_todoist_313_digest"
mkdir -p "$LOG_DIR"

cd "$REPO_DIR"
if [[ -f "${REPO_DIR}/.env.jarvis_private" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "${REPO_DIR}/.env.jarvis_private"
  set +a
fi

export TODOIST_313_AUTHOR="${TODOIST_313_AUTHOR:-FRIDAY}"

if [[ $# -gt 0 ]]; then
  # 手動: 週の整理（--weekly 以降をそのまま渡す。例: --weekly --undo list）
  if [[ "${1:-}" == "--weekly" ]]; then
    shift
    exec "$PY" "${REPO_DIR}/scripts/jarvis_todoist_313_weekly.py" "$@"
  fi
  # 手動: 従来 digest 引数を渡したいとき
  if [[ "${1:-}" == "--legacy-digest" ]]; then
    shift
    exec "$PY" "${REPO_DIR}/scripts/jarvis_todoist_313_digest.py" "$@"
  fi
  exec "$PY" "${REPO_DIR}/scripts/jarvis_todoist_313_cleanup.py" "$@"
fi

# 本線（2026-11-24〜・松野さん了承）: 週1回・金曜の夜だけ「313 週の整理」
#   A 済みました（根拠のはっきりした件を閉じる）＋ B やめる提案（/313/bulk）＋ #consult に1通
# 毎晩の片付け（期日ずらしの3択）はやめた。期日は土曜の「今週の9件」で決める。
# plist がまだ毎日 20:00 のままでも、金曜以外はここで何もせず終える（入れ替え前の安全弁）
DOW="$(TZ=Asia/Tokyo date +%u)"  # 1=月 … 5=金
if [[ "$DOW" != "5" && "${T313_WEEKLY_FORCE:-}" != "1" ]]; then
  echo "313: 今日は金曜ではないので何もしません（週の整理は金曜 20:00）"
  exit 0
fi
"$PY" "${REPO_DIR}/scripts/jarvis_todoist_313_weekly.py" --apply
