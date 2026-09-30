#!/bin/zsh
# Jarvis: ~/git-repos → OneDrive 疎ミラー（週次・日曜 09:15）
set -euo pipefail
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
LOG_DIR="${HOME}/Library/Logs/jarvis_repo_mirror"
mkdir -p "$LOG_DIR"
STAMP="$(date +%Y%m%d_%H%M%S)"
LOG="${LOG_DIR}/mirror_${STAMP}.log"

export PATH="${HOME}/bin:/opt/homebrew/bin:/usr/local/bin:${PATH}"
cd "$REPO_DIR"

{
  echo "# start $(date '+%Y-%m-%d %H:%M:%S %z')"
  "${REPO_DIR}/scripts/jarvis_repo_onedrive_mirror.sh" --apply
  echo "# end exit=$?"
} >>"$LOG" 2>&1

# 直近 30 世代だけ残す
ls -1t "${LOG_DIR}"/mirror_*.log 2>/dev/null | tail -n +31 | while IFS= read -r f; do rm -f "$f"; done
