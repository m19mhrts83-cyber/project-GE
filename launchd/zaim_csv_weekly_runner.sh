#!/bin/zsh
# Jarvis: Zaim CSV 火・金 12:00 エクスポート → finance / energy metrics push
# （Mac 朝オープン時の取りこぼしフォールバックからも呼ばれる）
# ログ: ~/Library/Logs/jarvis_zaim/
#
# 教訓（2026-09）:
# - source .env 前に set -u だと $ を含むパスワードで落ちる
# - OneDrive CSV 直後の読取は Resource deadlock になりやすい → ローカルコピー＋再試行
# - export 成功後の push 失敗で last_ok=false にしない（失敗理由を分類して state に残す）
set -euo pipefail
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
ZAIM_DIR="${REPO_DIR}/215_kamiooya/C1_cursor/finance/zaim_budget_sync"
PY="${HOME}/selenium_env/venv/bin/python"
LOG_DIR="${HOME}/Library/Logs/jarvis_zaim"
STATE_DIR="${REPO_DIR}/.jarvis_state"
STATE_JSON="${STATE_DIR}/zaim_csv_weekly.json"
LOCAL_CSV_DIR="${ZAIM_DIR}/downloads"
mkdir -p "$LOG_DIR" "$STATE_DIR" "$LOCAL_CSV_DIR"
STAMP="$(date +%Y%m%d_%H%M%S)"
LOG="${LOG_DIR}/weekly_${STAMP}.log"
YEAR="$(date +%Y)"
END_DATE="$(date +%Y-%m-%d)"
NOW_ISO="$(date +%Y-%m-%dT%H:%M:%S%z)"

cd "$REPO_DIR"
# nounset を一時解除してから env を読む（$ を含む値対策）
if [[ -f "${REPO_DIR}/.env.jarvis_private" ]]; then
  set +u
  set -a
  # shellcheck disable=SC1091
  source "${REPO_DIR}/.env.jarvis_private" 2>/dev/null || true
  set +a
  set -u
fi

write_state() {
  local ok="$1"
  local msg="$2"
  local csv_path="$3"
  local err_kind="${4:-}"
  "$PY" - "$STATE_JSON" "$ok" "$msg" "$csv_path" "$NOW_ISO" "$YEAR" "$END_DATE" "$err_kind" <<'PY'
import json, sys
from pathlib import Path
path, ok, msg, csv_path, now, year, end, err_kind = sys.argv[1:9]
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
if err_kind:
    data["last_error_kind"] = err_kind
if ok == "1":
    data["last_success_at"] = now
    data["last_error"] = None
    data["last_error_kind"] = None
else:
    data["last_error"] = msg[:500]
    data["last_error_at"] = now
p.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
PY
}

classify_export_error() {
  local log_snip
  log_snip="$(tail -n 40 "$LOG" 2>/dev/null || true)"
  if print -r -- "$log_snip" | grep -qiE 'session_missing|STORAGE_STATE|先に.*login|ログイン完了を待ちましたが'; then
    print -r -- "session_expired"
  elif print -r -- "$log_snip" | grep -qiE 'ERR_NETWORK_CHANGED|net::ERR_|TimeoutError|Timeout [0-9]+ms'; then
    print -r -- "network_transient"
  elif print -r -- "$log_snip" | grep -qiE 'Resource deadlock|Errno 11'; then
    print -r -- "onedrive_deadlock"
  else
    print -r -- "export_failed"
  fi
}

CSV_OUT="${HOME}/Library/CloudStorage/OneDrive-個人用/215_神・大家さん倶楽部/50_税金,確定申告/${YEAR}年度/Zaim.${YEAR}年度.csv"
LOCAL_CSV="${LOCAL_CSV_DIR}/Zaim.${YEAR}年度.local_copy.csv"

{
  echo "# start ${NOW_ISO}"
  echo "# year=${YEAR} end_date=${END_DATE}"

  if [[ ! -f "${ZAIM_DIR}/.zaim_storage_state.json" ]]; then
    echo "# ERROR: Zaim セッションなし。.zaim_storage_state.json がありません。"
    echo "# 再ログイン: cd ${ZAIM_DIR} && ${PY} zaim_budget_apply.py --login --login-method email"
    write_state "0" "session_missing: run zaim_budget_apply.py --login" "" "session_expired"
    exit 1
  fi

  set +e
  "$PY" "${ZAIM_DIR}/zaim_csv_export.py" \
    --year "$YEAR" \
    --end-date "$END_DATE" \
    --headless \
    --login-method email \
    --retries 2
  EXP_RC=$?
  set -e

  if [[ "$EXP_RC" -ne 0 ]]; then
    KIND="$(classify_export_error)"
    echo "# ERROR: zaim_csv_export failed rc=${EXP_RC} kind=${KIND}"
    case "$KIND" in
      session_expired)
        echo "# セッション切れの可能性。再ログイン:"
        echo "#   cd ${ZAIM_DIR} && ${PY} zaim_budget_apply.py --login --login-method email"
        write_state "0" "export_failed rc=${EXP_RC} kind=session_expired（要ログイン）" "" "$KIND"
        ;;
      network_transient)
        echo "# ネットワーク一時障害。数分後に再実行可（再ログイン不要のことが多い）"
        write_state "0" "export_failed rc=${EXP_RC} kind=network_transient（ERR_NETWORK / timeout）" "" "$KIND"
        ;;
      *)
        write_state "0" "export_failed rc=${EXP_RC} kind=${KIND}" "" "$KIND"
        ;;
    esac
    exit "$EXP_RC"
  fi

  if [[ ! -f "$CSV_OUT" ]]; then
    echo "# ERROR: CSV が見つかりません: ${CSV_OUT}"
    write_state "0" "csv_missing after export" "" "csv_missing"
    exit 1
  fi

  echo "# export ok → ${CSV_OUT}"
  # OneDrive 直読の deadlock 回避: ローカルへコピーしてから metrics
  set +e
  cp -f "$CSV_OUT" "$LOCAL_CSV"
  CP_RC=$?
  set -e
  METRICS_CSV="$CSV_OUT"
  if [[ "$CP_RC" -eq 0 && -f "$LOCAL_CSV" ]]; then
    METRICS_CSV="$LOCAL_CSV"
    echo "# local copy for metrics → ${LOCAL_CSV}"
    export ZAIM_CSV_OVERRIDE="$LOCAL_CSV"
  fi

  PUSH_OK=1
  set +e
  for attempt in 1 2 3; do
    if [[ -n "${ZAIM_CSV_OVERRIDE:-}" ]]; then
      ZAIM_CSV_PATH="$METRICS_CSV" "$PY" "${REPO_DIR}/scripts/jarvis_finance_metrics.py" --year "$YEAR" --push
    else
      "$PY" "${REPO_DIR}/scripts/jarvis_finance_metrics.py" --year "$YEAR" --push
    fi
    FM_RC=$?
    if [[ "$FM_RC" -eq 0 ]]; then
      break
    fi
    echo "# finance_metrics retry ${attempt} rc=${FM_RC}"
    sleep 3
  done
  if [[ "$FM_RC" -ne 0 ]]; then
    PUSH_OK=0
    echo "# WARN: finance_metrics failed after retries rc=${FM_RC}"
  fi
  "$PY" "${REPO_DIR}/scripts/jarvis_finance_metrics.py" --year "$((YEAR - 1))" --push
  for attempt in 1 2 3; do
    "$PY" "${REPO_DIR}/scripts/jarvis_energy_cf_collect.py" --push
    EN_RC=$?
    if [[ "$EN_RC" -eq 0 ]]; then
      break
    fi
    echo "# energy_cf retry ${attempt} rc=${EN_RC}"
    sleep 2
  done
  if [[ "$EN_RC" -ne 0 ]]; then
    PUSH_OK=0
  fi
  "$PY" "${REPO_DIR}/scripts/jarvis_zaim_watch_runner.py" --skip-finance
  "$PY" "${REPO_DIR}/scripts/jarvis_mq_monthly_refresh.py"
  "$PY" "${REPO_DIR}/scripts/jarvis_airwallet_banks_weekly.py"
  "$PY" "${REPO_DIR}/scripts/jarvis_situation_watch.py" --write
  "$PY" "${REPO_DIR}/scripts/jarvis_dashboard_push.py" --watch-only
  "$PY" "${REPO_DIR}/scripts/jarvis_zaim_refresh_queue_poll.py" --ack-only
  set -e

  if [[ "$PUSH_OK" -eq 1 ]]; then
    write_state "1" "export+push ok" "$CSV_OUT" ""
  else
    # export 自体は成功。push 一部失敗でも last_ok=true（CSV 正本は新しい）
    write_state "1" "export ok · push partial fail（ログ参照・再実行可）" "$CSV_OUT" "push_partial"
  fi
  echo "# end ok $(date '+%Y-%m-%d %H:%M:%S %z') push_ok=${PUSH_OK}"
} >>"$LOG" 2>&1
