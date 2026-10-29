#!/bin/zsh
# 神大家 講座動画の週次取込（日曜 12:00）。字幕→Whisper→差分登録→Notta差し替え→誤記候補（AI 使用料ゼロ）
set -euo pipefail
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_DIR"
[[ "${KAMIOOYA_VIDEO_WEEKLY_DISABLE:-0}" == "1" ]] && { echo "disabled"; exit 0; }
export PATH="$HOME/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"
emulate -R sh -c "set -a; . '${REPO_DIR}/.env.jarvis_private'; set +a" 2>/dev/null || true
PY="${JARVIS_PYTHON:-/Users/matsunomasaharu2/selenium_env/venv/bin/python}"
# ffmpeg は jarvis_westudy_whisper_fallback.py が venv の imageio-ffmpeg から用意する（実体名が ffmpeg ではないため PATH 追加だけでは見つからない）
# スリープで止まらないように caffeinate で包む
exec caffeinate -i "$PY" "$REPO_DIR/scripts/kamiooya_video_weekly.py" --post
