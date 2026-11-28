#!/bin/zsh
# Jarvis Dashboard → Supabase 日次 push（lanes/finance 含む）
# 先頭でカード引落ウォッチを更新し、situation_watch 経由でピンに載せる
set -euo pipefail
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PY="${HOME}/selenium_env/venv/bin/python"
LOG_DIR="${HOME}/Library/Logs/jarvis_dashboard"
mkdir -p "$LOG_DIR"
STAMP="$(date +%Y%m%d_%H%M%S)"
LOG="${LOG_DIR}/push_${STAMP}.log"

cd "$REPO_DIR"
if [[ -f "${REPO_DIR}/.env.jarvis_private" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "${REPO_DIR}/.env.jarvis_private"
  set +a
fi

{
  echo "# start $(date '+%Y-%m-%d %H:%M:%S %z')"
  # P0: カード引落収集（金額未確定なら Vpass も試す。失敗しても push は続ける）
  "$PY" "${REPO_DIR}/scripts/jarvis_card_debit_watch.py" --fetch-vpass-if-pending || echo "# card_debit_watch exit=$? (continue)"
  # WeStudy 取込 CI の連続成功は --mark-checked でしか進まず、人が回さないと state が古いまま「失敗」と出続けた（314 2026-11-28）。ここで毎回進める（同じ run は重複カウントしない）
  "$PY" "${REPO_DIR}/scripts/jarvis_westudy_weekly_check.py" --mark-checked >/dev/null || echo "# westudy_weekly_check exit=$? (continue)"
  "$PY" "${REPO_DIR}/scripts/jarvis_situation_watch.py" || echo "# situation_watch exit=$? (continue)"
  "$PY" "${REPO_DIR}/scripts/jarvis_dashboard_push.py"
  # 611: AI 使用量のいまの値を /ai-usage へ写す（失敗しても push 本体は成功扱い）
  "$PY" "${REPO_DIR}/scripts/jarvis_ai_usage_snapshot.py" --push >/dev/null || echo "# ai_usage_snapshot exit=$? (continue)"
  # Phase L: 814/815 鮮度を Slack #ops へ（失敗しても push 本体は成功扱い）
  if [[ "${JARVIS_UI_CYCLE_DISABLE:-}" != "1" ]]; then
    "$PY" "${REPO_DIR}/scripts/jarvis_ui_cycle_814_815.py" --agent both --post || echo "# ui_cycle_814_815 exit=$? (continue)"
  fi
  echo "# end exit=$?"
} >>"$LOG" 2>&1
