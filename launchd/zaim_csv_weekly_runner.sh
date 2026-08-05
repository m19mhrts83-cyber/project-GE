#!/bin/zsh
# Jarvis: Zaim CSV 火・金 12:00 エクスポート → finance / energy metrics push
# （Mac 朝オープン時の取りこぼしフォールバックからも呼ばれる）
# ログ: ~/Library/Logs/jarvis_zaim/
set -euo pipefail
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
ZAIM_DIR="${REPO_DIR}/215_kamiooya/C1_cursor/finance/zaim_budget_sync"
PY="${HOME}/selenium_env/venv/bin/python"
LOG_DIR="${HOME}/Library/Logs/jarvis_zaim"
STATE_DIR="${REPO_DIR}/.jarvis_state"
STATE_JSON="${STATE_DIR}/zaim_csv_weekly.json"
mkdir -p "$LOG_DIR" "$STATE_DIR"
STAMP="$(date +%Y%m%d_%H%M%S)"
LOG="${LOG_DIR}/weekly_${STAMP}.log"
YEAR="$(date +%Y)"
END_DATE="$(date +%Y-%m-%d)"
NOW_ISO="$(date +%Y-%m-%dT%H:%M:%S%z)"

cd "$REPO_DIR"
if [[ -f "${REPO_DIR}/.env.jarvis_private" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "${REPO_DIR}/.env.jarvis_private"
  set +a
fi

write_state() {
  local ok="$1"
  local msg="$2"
  local csv_path="$3"
  "$PY" - "$STATE_JSON" "$ok" "$msg" "$csv_path" "$NOW_ISO" "$YEAR" "$END_DATE" <<'PY'
import json, sys
from pathlib import Path
path, ok, msg, csv_path, now, year, end = sys.argv[1:8]
prev = {}
p = Path(path)
if p.is_file():
    try:
        prev = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        prev = {}
data = {
    **prev,
    "updated_at": now,
    "year": int(year),
    "end_date": end,
    "last_ok": ok == "1",
    "last_message": msg[:500],
    "csv_path": csv_path or prev.get("csv_path"),
}
if ok == "1":
    data["last_success_at"] = now
    data["last_error"] = None
else:
    data["last_error"] = msg[:500]
    data["last_error_at"] = now
p.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
PY
}

CSV_OUT="${HOME}/Library/CloudStorage/OneDrive-個人用/215_神・大家さん倶楽部/50_税金,確定申告/${YEAR}年度/Zaim.${YEAR}年度.csv"

{
  echo "# start ${NOW_ISO}"
  echo "# year=${YEAR} end_date=${END_DATE}"

  if [[ ! -f "${ZAIM_DIR}/.zaim_storage_state.json" ]]; then
    echo "# ERROR: Zaim セッションなし。.zaim_storage_state.json がありません。"
    echo "# 再ログイン: cd ${ZAIM_DIR} && ${PY} zaim_budget_apply.py --login --login-method email"
    write_state "0" "session_missing: run zaim_budget_apply.py --login" ""
    exit 1
  fi

  set +e
  "$PY" "${ZAIM_DIR}/zaim_csv_export.py" \
    --year "$YEAR" \
    --end-date "$END_DATE" \
    --headless \
    --login-method email
  EXP_RC=$?
  set -e

  if [[ "$EXP_RC" -ne 0 ]]; then
    echo "# ERROR: zaim_csv_export failed rc=${EXP_RC}"
    echo "# セッション切れの可能性。再ログイン:"
    echo "#   cd ${ZAIM_DIR} && set -a && source ${REPO_DIR}/.env.jarvis_private && set +a"
    echo "#   ${PY} zaim_budget_apply.py --login --login-method email"
    echo "#   （CDP 推奨）--connect-cdp http://127.0.0.1:9223"
    write_state "0" "export_failed rc=${EXP_RC} (可能: ログイン切れ)" ""
    exit "$EXP_RC"
  fi

  if [[ ! -f "$CSV_OUT" ]]; then
    echo "# ERROR: CSV が見つかりません: ${CSV_OUT}"
    write_state "0" "csv_missing after export" ""
    exit 1
  fi

  echo "# export ok → ${CSV_OUT}"
  "$PY" "${REPO_DIR}/scripts/jarvis_finance_metrics.py" --year "$YEAR" --push
  # 前年CSVがあれば年間比較用に push（無ければ非0でも続行）
  set +e
  "$PY" "${REPO_DIR}/scripts/jarvis_finance_metrics.py" --year "$((YEAR - 1))" --push
  set -e
  "$PY" "${REPO_DIR}/scripts/jarvis_energy_cf_collect.py" --push
  # Zaim Watch: 二重取込の安全自動適用 → 状況ウォッチ push
  set +e
  "$PY" "${REPO_DIR}/scripts/jarvis_zaim_watch_runner.py" --skip-finance
  set -e

  write_state "1" "export+push ok" "$CSV_OUT"
  echo "# end ok $(date '+%Y-%m-%d %H:%M:%S %z')"
} >>"$LOG" 2>&1
