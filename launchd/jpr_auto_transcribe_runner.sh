#!/bin/zsh
# Just Press Record 未文字起こしの自動処理（1時間ごと・AIチャット不使用・Gemini 無料枠）
set -euo pipefail
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_DIR"
# GEMINI_API_KEY を読む。値は出さない
if [[ -f "$REPO_DIR/.env.jarvis_private" ]]; then set -a; source "$REPO_DIR/.env.jarvis_private" >/dev/null 2>&1; set +a; fi
PY="${JARVIS_PYTHON:-/Users/matsunomasaharu2/selenium_env/venv/bin/python}"
exec "$PY" "$REPO_DIR/scripts/jarvis_jpr_auto_transcribe.py"
