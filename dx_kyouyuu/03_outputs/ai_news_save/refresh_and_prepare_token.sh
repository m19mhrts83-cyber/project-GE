#!/usr/bin/env bash
# Gmail token を更新し、GitHub Secret 用の Base64 をクリップボードとファイルに用意する。
# 使い方: ./refresh_and_prepare_token.sh
# その後は GitHub の GMAIL_TOKEN_B64 に貼り付けて更新するだけ。

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_PYTHON="/Users/matsunomasaharu/Library/CloudStorage/OneDrive-個人用/215_神・大家さん倶楽部/C1_cursor/1b_Cursorマニュアル/.venv_gmail/bin/python"
TOKEN_JSON="/Users/matsunomasaharu/Library/CloudStorage/OneDrive-個人用/215_神・大家さん倶楽部/C1_cursor/1b_Cursorマニュアル/token.json"

cd "$SCRIPT_DIR"
echo "1. Gmail token を確認・更新しています..."
if ! "$VENV_PYTHON" gmail_ai_news_save.py --list; then
  echo ""
  echo "   ※ ブラウザで認証が求められた場合は、ターミナルでこのスクリプトを実行して認証を完了してください。"
  echo "   ※ 認証後、もう一度 ./refresh_and_prepare_token.sh を実行してください。"
  exit 1
fi

if [[ ! -f "$TOKEN_JSON" ]]; then
  echo "エラー: token.json が見つかりません。215 の 1b_Cursorマニュアル で credentials.json を確認してください。"
  exit 1
fi

echo ""
echo "2. Base64 をクリップボードにコピーし、ファイルにも書き出しました。"
base64 -i "$TOKEN_JSON" | tr -d '\n' | pbcopy
B64_FILE="$SCRIPT_DIR/token_for_github_secret_b64.txt"
base64 -i "$TOKEN_JSON" | tr -d '\n' > "$B64_FILE"
echo "   ファイル: token_for_github_secret_b64.txt"
echo ""
echo "3. 次のステップ:"
echo "   - リポジトリの Settings → Secrets and variables → Actions を開く"
echo "   - GMAIL_TOKEN_B64 の Update をクリック"
echo "   - Value に貼り付け (Cmd+V) → Update secret"
echo ""
echo "完了しました。GitHub で Secret を更新してください。"
