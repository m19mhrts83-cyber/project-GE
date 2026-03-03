#!/bin/bash
# メール送信の簡易実行スクリプト

# スクリプトのディレクトリに移動
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# 引数チェック
if [ $# -lt 2 ]; then
    echo "使い方: $0 <MDファイル> <Excelファイル> [シート名] [メール列名]"
    echo ""
    echo "例:"
    echo "  $0 メール.md 送信先リスト.xlsx"
    echo "  $0 メール.md 送信先リスト.xlsx 送信先一覧 メールアドレス"
    exit 1
fi

MD_FILE="$1"
EXCEL_FILE="$2"
SHEET_NAME="${3:-}"
EMAIL_COLUMN="${4:-}"

# Pythonスクリプトの実行
CMD="python3 send_mail.py --md-file \"$MD_FILE\" --excel-file \"$EXCEL_FILE\""

if [ -n "$SHEET_NAME" ]; then
    CMD="$CMD --sheet-name \"$SHEET_NAME\""
fi

if [ -n "$EMAIL_COLUMN" ]; then
    CMD="$CMD --email-column \"$EMAIL_COLUMN\""
fi

echo "実行コマンド: $CMD"
echo ""
eval $CMD
