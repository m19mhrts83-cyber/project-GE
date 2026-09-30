#!/bin/zsh
# Jarvis 夜間メールトリアージ runner
set -euo pipefail
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PY="${HOME}/selenium_env/venv/bin/python"
LOG_DIR="${HOME}/Library/Logs/jarvis_night_triage"
mkdir -p "$LOG_DIR"

cd "$REPO_DIR"
if [[ -f "${REPO_DIR}/.env.jarvis_private" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "${REPO_DIR}/.env.jarvis_private"
  set +a
fi

# パートナー Gmail／Chatwork 判定は GHA 本線。未設定時もスキップ（=0 で Mac 判定に戻す）
EXTRA=()
if [[ "${JARVIS_NIGHT_TRIAGE_SKIP_PARTNER_GMAIL:-1}" != "0" ]]; then
  EXTRA+=(--skip-partner-gmail)
fi
if [[ "${JARVIS_NIGHT_TRIAGE_SKIP_PARTNER_CHATWORK:-1}" != "0" ]]; then
  EXTRA+=(--skip-partner-chatwork)
fi

exec "$PY" "${REPO_DIR}/scripts/jarvis_night_triage.py" "${EXTRA[@]}" "$@"
