#!/bin/zsh
# Vポイント Tサイト履歴の定期取得（毎月24日 08:30 JST・窓C前日）
# 窓C（25〜月末 09:40 の vpoint-routine）が読む履歴を、その前日に取り直す。
# 認証（V会員番号＋メールOTP）は本人のメールを Gmail API で読むだけ。迂回しない。
# 失敗は #ops に1日1回。定例は壊さない。再試行は1日1回まで。
# スリープで朝に動かなかった時は、launchd が復帰時に1回実行する（新しい常駐は作らない）。
# 停止: JARVIS_VPOINT_TSITE_FETCH_DISABLE=1（.env.jarvis_private）
set -euo pipefail
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PY="${HOME}/selenium_env/venv/bin/python"
LOG_DIR="${HOME}/Library/Logs/jarvis_vpoint_tsite_fetch"
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

{
  echo "# start $(date '+%Y-%m-%d %H:%M:%S %z')"
  set +e
  "$PY" -u "${REPO_DIR}/scripts/jarvis_vpoint_tsite_scheduled.py"
  rc=$?
  set -e
  echo "# end exit=${rc}"
} >>"$LOG" 2>&1
exit 0
