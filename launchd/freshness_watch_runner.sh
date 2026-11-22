#!/bin/zsh
# 315 鮮度監視＋315-B 停止・空回り監視（1 日 2 回）。古くなった／回復したときだけ #ops（AI なし）
set -euo pipefail
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_DIR"
# gh は ~/bin にある（launchd の PATH には入らない）
export PATH="$HOME/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"
emulate -R sh -c "set -a; . '${REPO_DIR}/.env.jarvis_private'; set +a" 2>/dev/null || true
PY="${JARVIS_PYTHON:-/Users/matsunomasaharu2/selenium_env/venv/bin/python}"
# 既存の鮮度監視と 315-B（300番台 停止・空回り）を続けて回す。片方が落ちてももう片方は回す
rc=0
"$PY" "$REPO_DIR/scripts/jarvis_freshness_watch.py" --post || rc=$?
# 315-B: 0=成功 2=部分成功 1=失敗（結果は .jarvis_state/stall_watch_315b.json とダッシュボード）
"$PY" "$REPO_DIR/scripts/jarvis_stall_watch_315b.py" --post || { r=$?; [ "$rc" -eq 0 ] && rc=$r; }
# 611: AI 使用量のいまの値をダッシュボード（/ai-usage）へ写す。失敗しても監視の結果は変えない
"$PY" "$REPO_DIR/scripts/jarvis_ai_usage_snapshot.py" --push >/dev/null || echo "# ai_usage_snapshot exit=$? (continue)" >&2
exit "$rc"
