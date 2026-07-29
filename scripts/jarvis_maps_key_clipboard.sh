#!/bin/zsh
# Copy GOOGLE_MAPS_API_KEY to clipboard (does not echo the key)
set -e
cd "$(dirname "$0")/.."
set -a
source .env.jarvis_private
set +a
if [[ -z "${GOOGLE_MAPS_API_KEY:-}" ]]; then
  echo "GOOGLE_MAPS_API_KEY が空です。.env.jarvis_private に追記してください。"
  exit 1
fi
print -n -- "$GOOGLE_MAPS_API_KEY" | pbcopy
echo "📎 クリップボードにコピーしました（チャットには出しません）。shuhen-map の API Key 欄に貼り付けてください。"
