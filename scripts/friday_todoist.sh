#!/bin/zsh
# FRIDAY / Jarvis 共用: Todoist CLI を秘密をチャットに出さず実行する。
#
# 使い方:
#   cd ~/git-repos
#   ./scripts/friday_todoist.sh whoami
#   ./scripts/friday_todoist.sh lane --id apps
#   ./scripts/friday_todoist.sh update-status --task-id … --lane apps --status オーナー確認
#   ./scripts/friday_todoist.sh comment --task-id … --text 'サマリ: …'
#   ./scripts/friday_todoist.sh complete-task --lane apps --task-id … \
#     --comment 'タスク完了したよ（FRIDAY・松野確認OK）'
#
# 方針:
# - トークンは .env.jarvis_private の TODOIST_API_TOKEN（Jarvis 分身）を内部で読む
# - FRIDAY は .env を cat／チャット貼付しない（このラッパー経由のみ）
# - 完了は必ずオーナー確認 → 松野了承後（jarvis-todoist-owner-confirm.mdc）
set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO"

ENV_FILE="$REPO/.env.jarvis_private"
PY="${JARVIS_PYTHON:-/Users/matsunomasaharu2/selenium_env/venv/bin/python}"
CLI="$REPO/scripts/jarvis_todoist_api.py"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "[friday-todoist][ERROR] missing $ENV_FILE" >&2
  exit 2
fi
if [[ ! -x "$PY" && ! -f "$PY" ]]; then
  echo "[friday-todoist][ERROR] python not found: $PY" >&2
  exit 2
fi
if [[ ! -f "$CLI" ]]; then
  echo "[friday-todoist][ERROR] missing $CLI" >&2
  exit 2
fi

set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

if [[ -z "${TODOIST_API_TOKEN:-}" ]]; then
  echo "[friday-todoist][ERROR] TODOIST_API_TOKEN unset in jarvis_private" >&2
  exit 2
fi

exec "$PY" "$CLI" "$@"
