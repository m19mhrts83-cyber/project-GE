#!/usr/bin/env bash
# WeStudy抽出→差分CSV生成→LIMO取込まで一気通貫で実行
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CHATBOT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ONEDRIVE_CHATBOT_ROOT="/Users/matsunomasaharu/Library/CloudStorage/OneDrive-個人用/215_神・大家さん倶楽部/C1_cursor/1c_神・大家さん倶楽部_AI推進/神・大家さん倶楽部情報Q&Aチャットボット"
OUTPUT_ROOT="${CHATBOT_OUTPUT_ROOT:-$ONEDRIVE_CHATBOT_ROOT}"
if [[ ! -d "$OUTPUT_ROOT" ]]; then
  echo "出力先ディレクトリが見つかりません: $OUTPUT_ROOT" >&2
  echo "CHATBOT_OUTPUT_ROOT を有効なOneDriveパスで設定してください。" >&2
  exit 2
fi
PIPELINE_SCRIPT="$SCRIPT_DIR/run_westudy_pipeline.sh"
UPLOAD_SCRIPT="$SCRIPT_DIR/upload_csv_to_limo.py"
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

usage() {
  cat <<'EOF'
使い方:
  ./scripts/run_update_and_import.sh [run_westudy_pipeline.sh に渡す引数]

概要:
  1) WeStudyスクレイプ〜差分CSV生成（run_westudy_pipeline.sh）
  2) 最新 delta_*.csv を LIMO 管理画面へ自動取込

例:
  ./scripts/run_update_and_import.sh
  ./scripts/run_update_and_import.sh --force
  ./scripts/run_update_and_import.sh --show

必要な環境変数:
  WESTUDY_USER, WESTUDY_PASS
  CHATBOT_OUTPUT_ROOT（任意。未設定時は OneDrive 固定パス）
  LIMO_APP_URL
  LIMO: LIMO_PORTAL_EMAIL/PASSWORD（推奨）または LIMO_ADMIN_EMAIL/PASSWORD（1段目）
        2段ログイン時は LIMO_APP_EMAIL / LIMO_APP_PASSWORD も必須（scripts/.env.example 参照）
EOF
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

exec > >(tee -a "$LOG_FILE") 2>&1

if [[ ! -x "$PIPELINE_SCRIPT" ]]; then
  echo "実行不可: $PIPELINE_SCRIPT" >&2
  exit 2
fi
if [[ ! -f "$UPLOAD_SCRIPT" ]]; then
  echo "アップロードスクリプトがありません: $UPLOAD_SCRIPT" >&2
  exit 2
fi

echo "==> step1: WeStudy更新パイプライン"
"$PIPELINE_SCRIPT" "$@"

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
if [[ "$DELTA_ROWS" -le 0 ]]; then
  echo "差分0件（ヘッダのみ）のため、LIMO取込はスキップします。"
  echo "log: $LOG_FILE"
  exit 0
fi

LIMO_PORTAL_OK=0
if [[ -n "${LIMO_PORTAL_EMAIL:-}" && -n "${LIMO_PORTAL_PASSWORD:-}" ]]; then
  LIMO_PORTAL_OK=1
elif [[ -z "${LIMO_PORTAL_EMAIL:-}" && -z "${LIMO_PORTAL_PASSWORD:-}" ]]; then
  if [[ -n "${LIMO_ADMIN_EMAIL:-}" && -n "${LIMO_ADMIN_PASSWORD:-}" ]]; then
    LIMO_PORTAL_OK=1
  fi
else
  echo "LIMO_PORTAL_EMAIL と LIMO_PORTAL_PASSWORD は両方セットするか、両方空にしてください。" >&2
  exit 2
fi

if [[ -z "${LIMO_APP_URL:-}" || "$LIMO_PORTAL_OK" -ne 1 ]]; then
  cat >&2 <<'EOF'
LIMO用環境変数が不足しています。以下を設定してください:
  export LIMO_APP_URL="https://.../"
  1段目（いずれかのペア）:
    export LIMO_PORTAL_EMAIL="..."  と  LIMO_PORTAL_PASSWORD="..."
    または（従来） LIMO_ADMIN_EMAIL / LIMO_ADMIN_PASSWORD
  2段目（ミニアプリのログインが別の場合）:
    export LIMO_APP_EMAIL="..."  と  LIMO_APP_PASSWORD="..."
EOF
  exit 2
fi

echo "==> step2: LIMOへ差分CSVを自動取り込み"
"$PYTHON" "$UPLOAD_SCRIPT" \
  --csv "$LATEST_DELTA" \
  --screenshot-dir "$OUTPUT_ROOT/exports/logs"

echo "完了: 抽出〜LIMO取込まで実行しました"
echo "delta: $LATEST_DELTA"
echo "log:   $LOG_FILE"
