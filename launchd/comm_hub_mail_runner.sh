#!/bin/zsh
# 台帳（comm hub）へメールを書き足す：要確認メール→inquiry、自分の送信→self（毎朝 5:45）
set -euo pipefail
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_DIR"
[[ "${JARVIS_COMM_HUB:-1}" == "0" ]] && { echo "disabled"; exit 0; }
export PATH="$HOME/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"
emulate -R sh -c "set -a; . '${REPO_DIR}/.env.jarvis_private'; set +a" 2>/dev/null || true
PY="${JARVIS_PYTHON:-/Users/matsunomasaharu2/selenium_env/venv/bin/python}"
"$PY" "$REPO_DIR/scripts/jarvis_comm_hub.py" ingest-mail-triage --days 14 --apply || echo "# comm hub soft-fail: ingest-triage"
"$PY" "$REPO_DIR/scripts/jarvis_comm_hub.py" ingest-mail-sent --account admin --account estate --days 3 --apply || echo "# comm hub soft-fail: ingest-sent"
