#!/usr/bin/env bash
# WeStudy 全件スクレイプ → 管理者形式全件CSV → 差分CSV（state 更新）
# 依存: Python3, Selenium, Chrome / chromedriver, 環境変数 WESTUDY_USER / WESTUDY_PASS
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
RUN_ID="$(date +%Y%m%d-%H%M%S)"

LOG_DIR="$OUTPUT_ROOT/exports/logs"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/pipeline_${RUN_ID}.log"

# ログをファイルにも残す（bash の process substitution）
exec > >(tee -a "$LOG_FILE") 2>&1

RAW_ROOT="$OUTPUT_ROOT/exports/raw"
STATE_ROOT="${CHATBOT_STATE_ROOT:-$OUTPUT_ROOT/state}"
STATE_SCRAPE="$STATE_ROOT/westudy_scrape"
STATE_DELTA="$STATE_ROOT/westudy_comment_ids.json"
mkdir -p "$RAW_ROOT" "$STATE_SCRAPE" "$STATE_ROOT"

SCRAPER="${WESTUDY_SCRAPER:-$HOME/git-repos/ProgramCode/alfred_python/westudy_forum_all.py}"
DEFAULT_PY="$HOME/git-repos/ProgramCode/venv/bin/python"
if [[ -x "$DEFAULT_PY" ]]; then
  PYTHON="${PYTHON:-$DEFAULT_PY}"
else
  PYTHON="${PYTHON:-python3}"
fi
CONVERT="$SCRIPT_DIR/convert_to_admin_csv.py"
# 変数名は DELTA にしない（macOS 既定の bash 3.2 で $DELTA_CSV と誤パースされる）
BUILD_DELTA_SCRIPT="$SCRIPT_DIR/build_delta_csv.py"

# set -a && source scripts/.env 忘れ・未保存だとプレースホルダのまま動くのを防ぐ
if [[ "${WESTUDY_USER:-}" == "your-westudy-login-id" ]]; then
  echo "エラー: WESTUDY_USER が .env.example のダミー値です。scripts/.env を実値で保存し、チャットボット直下で set -a && source scripts/.env && set +a を実行してください。" >&2
  exit 2
fi
if [[ "${WESTUDY_PASS:-}" == "your-westudy-login-password" ]]; then
  echo "エラー: WESTUDY_PASS が .env.example のダミー値です。scripts/.env を保存してください。" >&2
  exit 2
fi

MODE="full"
RAW_DIR=""

if [[ "${1:-}" == "--convert-only" ]]; then
  MODE="convert_only"
  shift
  if [[ $# -lt 1 ]]; then
    echo "使い方: $0 --convert-only <既存のrawディレクトリ>" >&2
    exit 2
  fi
  RAW_DIR="$(cd "$1" && pwd)"
  shift
elif [[ "${1:-}" == "--skip-scrape" ]]; then
  MODE="skip_scrape"
  shift
  if [[ $# -lt 1 ]]; then
    echo "使い方: $0 --skip-scrape <既存のrawディレクトリ> [scraperに渡す引数は不要]" >&2
    exit 2
  fi
  RAW_DIR="$(cd "$1" && pwd)"
  shift
fi

FULL_CSV="$OUTPUT_ROOT/exports/full_${RUN_ID}.csv"
DELTA_CSV="$OUTPUT_ROOT/exports/delta_${RUN_ID}.csv"

if [[ "$MODE" == "full" ]]; then
  RAW_DIR="$RAW_ROOT/$RUN_ID"
  mkdir -p "$RAW_DIR"
  echo "==> スクレイプ → $RAW_DIR"
  if [[ ! -f "$SCRAPER" ]]; then
    echo "スクレイパーが見つかりません: $SCRAPER（WESTUDY_SCRAPER で上書き可）" >&2
    exit 2
  fi
  "$PYTHON" "$SCRAPER" --output-root "$RAW_DIR" --state-dir "$STATE_SCRAPE" "$@"
elif [[ "$MODE" == "convert_only" || "$MODE" == "skip_scrape" ]]; then
  : # RAW_DIR 済み
else
  echo "内部エラー: MODE=$MODE" >&2
  exit 1
fi

if [[ ! -d "$RAW_DIR" ]]; then
  echo "RAW ディレクトリがありません: $RAW_DIR" >&2
  exit 2
fi

echo "==> 管理者形式へ変換 → $FULL_CSV"
"$PYTHON" "$CONVERT" --input-dir "$RAW_DIR" -o "$FULL_CSV" -v

echo "==> 差分CSV → ${DELTA_CSV}（state: ${STATE_DELTA}）"
"$PYTHON" "$BUILD_DELTA_SCRIPT" --full "$FULL_CSV" --state "$STATE_DELTA" --delta "$DELTA_CSV" --update-state

echo ""
echo "完了 RUN_ID=$RUN_ID"
echo "  raw:     $RAW_DIR"
echo "  full:    $FULL_CSV"
echo "  delta:   ${DELTA_CSV}"
echo "  log:     $LOG_FILE"
