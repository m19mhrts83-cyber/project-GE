#!/usr/bin/env bash
# WeStudy 全件スクレイプ → 管理者形式全件CSV → 差分CSV（state 更新）
# 依存: Python3, Selenium, Chrome / chromedriver, 環境変数 WESTUDY_USER / WESTUDY_PASS
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CHATBOT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
RUN_ID="$(date +%Y%m%d-%H%M%S)"

LOG_DIR="$CHATBOT_ROOT/exports/logs"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/pipeline_${RUN_ID}.log"

# ログをファイルにも残す（bash の process substitution）
exec > >(tee -a "$LOG_FILE") 2>&1

RAW_ROOT="$CHATBOT_ROOT/exports/raw"
STATE_SCRAPE="$CHATBOT_ROOT/state/westudy_scrape"
STATE_DELTA="$CHATBOT_ROOT/state/westudy_comment_ids.json"
mkdir -p "$RAW_ROOT" "$STATE_SCRAPE" "$CHATBOT_ROOT/state"

SCRAPER="${WESTUDY_SCRAPER:-$HOME/git-repos/ProgramCode/alfred_python/westudy_forum_all.py}"
PYTHON="${PYTHON:-python3}"
CONVERT="$SCRIPT_DIR/convert_to_admin_csv.py"
DELTA="$SCRIPT_DIR/build_delta_csv.py"

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

FULL_CSV="$CHATBOT_ROOT/exports/full_${RUN_ID}.csv"
DELTA_CSV="$CHATBOT_ROOT/exports/delta_${RUN_ID}.csv"

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

echo "==> 差分CSV → $DELTA_CSV（state: $STATE_DELTA）"
"$PYTHON" "$DELTA" --full "$FULL_CSV" --state "$STATE_DELTA" --delta "$DELTA_CSV" --update-state

echo ""
echo "完了 RUN_ID=$RUN_ID"
echo "  raw:     $RAW_DIR"
echo "  full:    $FULL_CSV"
echo "  delta:   $DELTA_CSV"
echo "  log:     $LOG_FILE"
