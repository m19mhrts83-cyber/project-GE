#!/usr/bin/env bash
# WeStudy抽出→差分CSV生成→LIMO取込まで一気通貫で実行
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CHATBOT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
PIPELINE_SCRIPT="$SCRIPT_DIR/run_westudy_pipeline.sh"
UPLOAD_SCRIPT="$SCRIPT_DIR/upload_csv_to_limo.py"
DEFAULT_PY="$HOME/git-repos/ProgramCode/venv/bin/python"
if [[ -x "$DEFAULT_PY" ]]; then
  PYTHON="${PYTHON:-$DEFAULT_PY}"
else
  PYTHON="${PYTHON:-python3}"
fi
RUN_ID="$(date +%Y%m%d-%H%M%S)"
LOG_DIR="$CHATBOT_ROOT/exports/logs"
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
  LIMO_APP_URL, LIMO_ADMIN_EMAIL, LIMO_ADMIN_PASSWORD
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

LATEST_DELTA="$(ls -1t "$CHATBOT_ROOT"/exports/delta_*.csv 2>/dev/null | head -n 1 || true)"
if [[ -z "${LATEST_DELTA}" ]]; then
  echo "delta CSV が見つかりません。処理を中断します。" >&2
  exit 2
fi

DELTA_LINES="$(wc -l < "$LATEST_DELTA" | tr -d ' ')"
echo "最新delta: $LATEST_DELTA (lines=$DELTA_LINES)"
if [[ "$DELTA_LINES" -le 1 ]]; then
  echo "差分0件（ヘッダのみ）のため、LIMO取込はスキップします。"
  echo "log: $LOG_FILE"
  exit 0
fi

if [[ -z "${LIMO_APP_URL:-}" || -z "${LIMO_ADMIN_EMAIL:-}" || -z "${LIMO_ADMIN_PASSWORD:-}" ]]; then
  cat >&2 <<'EOF'
LIMO用環境変数が不足しています。以下を設定してください:
  export LIMO_APP_URL="https://.../"
  export LIMO_ADMIN_EMAIL="..."
  export LIMO_ADMIN_PASSWORD="..."
EOF
  exit 2
fi

echo "==> step2: LIMOへ差分CSVを自動取り込み"
"$PYTHON" "$UPLOAD_SCRIPT" \
  --csv "$LATEST_DELTA" \
  --screenshot-dir "$CHATBOT_ROOT/exports/logs"

echo "完了: 抽出〜LIMO取込まで実行しました"
echo "delta: $LATEST_DELTA"
echo "log:   $LOG_FILE"
