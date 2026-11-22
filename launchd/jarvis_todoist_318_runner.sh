#!/bin/zsh
# 318 Todoist消化係 毎朝 10:30 の定時実行（launchd から呼ぶ）。まだ登録しない（移管手順で松野さんが決めてから）。
# - 朝枠の担当が 318 の時だけ動く（--trigger schedule。担当が 313 なら何もせず正常終了）
# - 既定は「読む・仕分け・内部ログ」だけ。載せる・送る・コメントは TODOIST_318_RUN_FLAGS に書いた時だけ
#   使える値: --publish --send-slack --write-comments（ほかの値があれば動かさない）
# - 停止: .jarvis_state/todoist_318/STOP を置く、または TODOIST_318_STOP=1
set -euo pipefail
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PY="${HOME}/selenium_env/venv/bin/python"
LOG_DIR="${HOME}/Library/Logs/jarvis_todoist_318"
mkdir -p "$LOG_DIR"
STAMP="$(date +%Y%m%d_%H%M%S)"
LOG="${LOG_DIR}/run_${STAMP}.log"

cd "$REPO_DIR"
export PYTHONUNBUFFERED=1
if [[ -f "${REPO_DIR}/.env.jarvis_private" ]]; then
  set +e
  set -a
  # shellcheck disable=SC1091
  source "${REPO_DIR}/.env.jarvis_private" 2>>"${LOG_DIR}/env_source.err.log"
  set +a
  set -e
fi

EXTRA=()
for f in ${=TODOIST_318_RUN_FLAGS:-}; do
  case "$f" in
    --publish|--send-slack|--write-comments) EXTRA+=("$f") ;;
    *) echo "# 想定外のフラグ（${f}）。動かさない" >>"$LOG"; exit 2 ;;
  esac
done

{
  echo "# start $(date '+%Y-%m-%d %H:%M:%S %z') flags=${EXTRA[*]:-なし}"
  set +e
  "$PY" -u "${REPO_DIR}/scripts/jarvis_todoist_318_triage.py" run --trigger schedule "${EXTRA[@]}"
  rc=$?
  set -e
  echo "# end exit=${rc}"
} >>"$LOG" 2>&1
exit 0
