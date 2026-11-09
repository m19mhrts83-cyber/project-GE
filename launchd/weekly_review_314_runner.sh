#!/bin/zsh
# 314 業務品質監査 — 週次の機械チェック（土曜 9:00）。判断・修正は 9:30 の Claude 定期タスク
set -euo pipefail
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_DIR"
# gh は ~/bin にある（launchd の PATH には入らない）
export PATH="$HOME/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"
set -a
# shellcheck disable=SC1091
source "$REPO_DIR/.env.jarvis_private"
set +a
PY="${JARVIS_PYTHON:-/Users/matsunomasaharu2/selenium_env/venv/bin/python}"
# 611 Cursor 使用量の自動取得（非公開 API。失敗しても 0 で返り、手入力値が残る）
"$PY" "$REPO_DIR/scripts/jarvis_cursor_usage_fetch.py" >/dev/null || echo "611 cursor_usage_fetch failed" >&2
# 611 AI 使用量の週次集計（相乗り。失敗しても 314 は止めない。Supabase へは写さない＝--push なし）
"$PY" "$REPO_DIR/scripts/jarvis_ai_usage_weekly.py" >/dev/null || echo "611 ai_usage_weekly failed" >&2
# ループウェア: 判断ログを機械で束ね、ルール候補（最大3件）を loopware「今週の学び」に置く（AI なし・失敗しても続ける）
mkdir -p "$REPO_DIR/.jarvis_state/loopware"
"$PY" "$REPO_DIR/scripts/jarvis_loopware_weekly.py" --publish \
  > "$REPO_DIR/.jarvis_state/loopware/weekly.md" 2>> "$REPO_DIR/.jarvis_state/loopware/weekly.err" || true
# 見張りファイルも更新（315 鮮度監視が weekly.published_at を見る）
"$PY" "$REPO_DIR/scripts/jarvis_loopware_status.py" >> "$REPO_DIR/.jarvis_state/loopware/weekly.err" 2>&1 || true
exec "$PY" "$REPO_DIR/scripts/jarvis_weekly_review_314.py" --post
