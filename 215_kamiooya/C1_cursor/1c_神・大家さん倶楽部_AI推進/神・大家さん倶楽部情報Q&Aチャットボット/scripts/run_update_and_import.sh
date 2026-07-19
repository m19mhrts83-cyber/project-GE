#!/usr/bin/env bash
# WeStudy抽出→差分CSV生成→Supabase upsert→Raimo取込まで一気通貫で実行
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CHATBOT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ONEDRIVE_CHATBOT_ROOT="/Users/matsunomasaharu2/Library/CloudStorage/OneDrive-個人用/215_神・大家さん倶楽部/C1_cursor/1c_神・大家さん倶楽部_AI推進/神・大家さん倶楽部情報Q&Aチャットボット"
OUTPUT_ROOT="${CHATBOT_OUTPUT_ROOT:-$ONEDRIVE_CHATBOT_ROOT}"
if [[ ! -d "$OUTPUT_ROOT" ]]; then
  echo "出力先ディレクトリが見つかりません: $OUTPUT_ROOT" >&2
  echo "CHATBOT_OUTPUT_ROOT を有効なOneDriveパスで設定してください。" >&2
  exit 2
fi
PIPELINE_SCRIPT="$SCRIPT_DIR/run_westudy_pipeline.sh"
UPLOAD_RAIMO_SCRIPT="$SCRIPT_DIR/upload_csv_to_raimo.py"
# 旧名フォールバック
if [[ ! -f "$UPLOAD_RAIMO_SCRIPT" && -f "$SCRIPT_DIR/upload_csv_to_limo.py" ]]; then
  UPLOAD_RAIMO_SCRIPT="$SCRIPT_DIR/upload_csv_to_limo.py"
fi
UPLOAD_SUPABASE_SCRIPT="$SCRIPT_DIR/upload_csv_to_supabase.py"
DEFAULT_PY="$HOME/git-repos/ProgramCode/venv/bin/python"
if [[ -x "$DEFAULT_PY" ]]; then
  PYTHON="${PYTHON:-$DEFAULT_PY}"
else
  PYTHON="${PYTHON:-python3}"
fi
RUN_ID="$(date +%Y%m%d-%H%M%S)"
LOG_DIR="$OUTPUT_ROOT/exports/logs"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/update_and_import_${RUN_ID}.log"

# RAIMO_* が正。未設定時は LIMO_*（後方互換）を使う
apply_raimo_env_aliases() {
  local pairs=(
    RAIMO_APP_URL:LIMO_APP_URL
    RAIMO_APP_EMAIL:LIMO_APP_EMAIL
    RAIMO_APP_PASSWORD:LIMO_APP_PASSWORD
    RAIMO_PORTAL_EMAIL:LIMO_PORTAL_EMAIL
    RAIMO_PORTAL_PASSWORD:LIMO_PORTAL_PASSWORD
    RAIMO_ADMIN_EMAIL:LIMO_ADMIN_EMAIL
    RAIMO_ADMIN_PASSWORD:LIMO_ADMIN_PASSWORD
    RAIMO_FAIL_OPEN:LIMO_FAIL_OPEN
  )
  local pair raimo limo
  for pair in "${pairs[@]}"; do
    raimo="${pair%%:*}"
    limo="${pair##*:}"
    if [[ -z "${!raimo:-}" && -n "${!limo:-}" ]]; then
      printf -v "$raimo" '%s' "${!limo}"
      export "$raimo"
    fi
  done
}

usage() {
  cat <<'EOF'
使い方:
  ./scripts/run_update_and_import.sh [run_westudy_pipeline.sh に渡す引数]

概要:
  1) WeStudyスクレイプ〜差分CSV生成（run_westudy_pipeline.sh）
  2) 最新 delta_*.csv を Supabase へ upsert（SUPABASE_URL 設定時）
  3) 最新 delta_*.csv を Raimo 管理画面へ自動取込

例:
  ./scripts/run_update_and_import.sh
  ./scripts/run_update_and_import.sh --force
  ./scripts/run_update_and_import.sh --show

必要な環境変数:
  WESTUDY_USER, WESTUDY_PASS
  CHATBOT_OUTPUT_ROOT（任意。未設定時は OneDrive 固定パス）
  Supabase（任意・設定時は step2 実行）:
    SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY（推奨）
  Raimo（任意・設定時は step3 実行。RAIMO_* が正。LIMO_* も可）:
    RAIMO_APP_URL
    公開URL（1段・推奨）: RAIMO_APP_EMAIL / RAIMO_APP_PASSWORD
    ポータル経由（2段）: RAIMO_PORTAL_* または RAIMO_ADMIN_*
EOF
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

apply_raimo_env_aliases

exec > >(tee -a "$LOG_FILE") 2>&1

if [[ ! -x "$PIPELINE_SCRIPT" ]]; then
  echo "実行不可: $PIPELINE_SCRIPT" >&2
  exit 2
fi
if [[ ! -f "$UPLOAD_RAIMO_SCRIPT" ]]; then
  echo "Raimoアップロードスクリプトがありません: $UPLOAD_RAIMO_SCRIPT" >&2
  exit 2
fi
if [[ ! -f "$UPLOAD_SUPABASE_SCRIPT" ]]; then
  echo "Supabaseアップロードスクリプトがありません: $UPLOAD_SUPABASE_SCRIPT" >&2
  exit 2
fi

BUILD_DELTA_SCRIPT="$SCRIPT_DIR/build_delta_csv.py"
STATE_DELTA="${CHATBOT_STATE_ROOT:-$OUTPUT_ROOT/state}/westudy_comment_ids.json"

echo "==> step1: WeStudy更新パイプライン"
"$PIPELINE_SCRIPT" --defer-state-update "$@"

LATEST_DELTA="$(ls -1t "$OUTPUT_ROOT"/exports/delta_*.csv 2>/dev/null | head -n 1 || true)"
if [[ -z "${LATEST_DELTA}" ]]; then
  echo "delta CSV が見つかりません。処理を中断します。" >&2
  exit 2
fi

DELTA_ROWS="$("$PYTHON" - <<'PY' "$LATEST_DELTA"
import csv, sys
path = sys.argv[1]
with open(path, newline='', encoding='utf-8-sig', errors='replace') as f:
    r = csv.DictReader(f)
    print(sum(1 for _ in r))
PY
)"
DELTA_LINES="$(wc -l < "$LATEST_DELTA" | tr -d ' ')"
echo "最新delta: $LATEST_DELTA (rows=$DELTA_ROWS, physical_lines=$DELTA_LINES)"
LATEST_FULL="$(ls -1t "$OUTPUT_ROOT"/exports/full_*.csv 2>/dev/null | head -n 1 || true)"

commit_state_after_success() {
  if [[ -z "${LATEST_FULL:-}" || ! -f "$LATEST_FULL" ]]; then
    echo "警告: 全件CSVが見つからないため state を更新できません。" >&2
    return 1
  fi
  echo "==> state 更新（Raimo 取込成功または差分0件のため）"
  "$PYTHON" "$BUILD_DELTA_SCRIPT" \
    --full "$LATEST_FULL" \
    --state "$STATE_DELTA" \
    --delta "$LATEST_DELTA" \
    --update-state
}

if [[ "$DELTA_ROWS" -le 0 ]]; then
  echo "差分0件（ヘッダのみ）のため、Supabase/Raimo取込はスキップします。"
  commit_state_after_success || true
  echo "log: $LOG_FILE"
  exit 0
fi

SUPABASE_CONFIGURED=0
if [[ -n "${SUPABASE_URL:-}" ]]; then
  if [[ -n "${SUPABASE_SERVICE_ROLE_KEY:-}" || -n "${SUPABASE_ANON_KEY:-}" ]]; then
    SUPABASE_CONFIGURED=1
  fi
fi

if [[ "$SUPABASE_CONFIGURED" -eq 1 ]]; then
  echo "==> step2: Supabaseへ差分CSVを upsert"
  if ! "$PYTHON" "$UPLOAD_SUPABASE_SCRIPT" --csv "$LATEST_DELTA"; then
    if [[ "${SUPABASE_FAIL_OPEN:-0}" == "1" ]]; then
      echo "警告: Supabase取込に失敗しましたが、SUPABASE_FAIL_OPEN=1 のため処理を継続します。" >&2
    else
      echo "Supabase取込失敗。state は更新しません。" >&2
      exit 2
    fi
  fi
else
  echo "Supabase環境変数未設定のため、Supabase取込はスキップします。"
fi

RAIMO_APP_OK=0
if [[ -n "${RAIMO_APP_EMAIL:-}" && -n "${RAIMO_APP_PASSWORD:-}" ]]; then
  RAIMO_APP_OK=1
fi
RAIMO_PORTAL_OK=0
if [[ -n "${RAIMO_PORTAL_EMAIL:-}" && -n "${RAIMO_PORTAL_PASSWORD:-}" ]]; then
  RAIMO_PORTAL_OK=1
elif [[ -z "${RAIMO_PORTAL_EMAIL:-}" && -z "${RAIMO_PORTAL_PASSWORD:-}" ]]; then
  if [[ -n "${RAIMO_ADMIN_EMAIL:-}" && -n "${RAIMO_ADMIN_PASSWORD:-}" ]]; then
    RAIMO_PORTAL_OK=1
  fi
else
  echo "RAIMO_PORTAL_EMAIL と RAIMO_PORTAL_PASSWORD は両方セットするか、両方空にしてください。" >&2
  exit 2
fi

if [[ -z "${RAIMO_APP_URL:-}" || ( "$RAIMO_APP_OK" -ne 1 && "$RAIMO_PORTAL_OK" -ne 1 ) ]]; then
  if [[ "$SUPABASE_CONFIGURED" -eq 1 ]]; then
    echo "Raimo用環境変数が不足のため Raimo 取込はスキップします（Supabase のみ実行）。"
    commit_state_after_success
    echo "完了: Supabase取込まで実行しました"
    echo "delta: $LATEST_DELTA"
    echo "log:   $LOG_FILE"
    exit 0
  fi
  cat >&2 <<'EOF'
Raimo用環境変数が不足しています。以下を設定してください:
  export RAIMO_APP_URL="https://.../"
  公開URL（1段・推奨）:
    export RAIMO_APP_EMAIL="..."  と  RAIMO_APP_PASSWORD="..."
  従来のポータル経由（2段）の場合のみ:
    export RAIMO_PORTAL_EMAIL="..."  と  RAIMO_PORTAL_PASSWORD="..."
    （必要なら RAIMO_APP_EMAIL / RAIMO_APP_PASSWORD も）

（後方互換: LIMO_* でも可）
Supabase のみ取込する場合は SUPABASE_URL と SUPABASE_SERVICE_ROLE_KEY を設定してください。
EOF
  exit 2
fi

echo "==> step3: Raimoへ差分CSVを自動取り込み"
if ! "$PYTHON" "$UPLOAD_RAIMO_SCRIPT" \
  --csv "$LATEST_DELTA" \
  --screenshot-dir "$OUTPUT_ROOT/exports/logs"; then
  if [[ "${RAIMO_FAIL_OPEN:-0}" == "1" ]]; then
    echo "警告: Raimo取込に失敗しましたが、RAIMO_FAIL_OPEN=1 のため処理を継続します。" >&2
    echo "確認ログ: $LOG_FILE" >&2
    exit 0
  fi
  exit 2
fi

commit_state_after_success

echo "完了: 抽出〜Supabase/Raimo取込まで実行しました"
echo "delta: $LATEST_DELTA"
echo "log:   $LOG_FILE"
