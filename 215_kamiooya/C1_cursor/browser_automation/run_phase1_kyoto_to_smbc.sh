#!/bin/zsh
# Wave3: 京都銀行 → SMBC刈谷 50,000円
set -euo pipefail
MODE=""
EXTRA=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    --preview) MODE=preview; shift ;;
    --go) MODE=go; shift ;;
    --execute) EXTRA+=(--execute); shift ;;
    --no-hold) EXTRA+=(--no-hold); shift ;;
    --money-ops-id) EXTRA+=(--money-ops-id "$2"); shift 2 ;;
    --balance) EXTRA+=(--balance "$2"); shift 2 ;;
    -h|--help) echo "Usage: $0 --preview|--go [--execute]"; exit 0 ;;
    *) echo "unknown $1" >&2; exit 2 ;;
  esac
done
[[ -n "$MODE" ]] || { echo "need --preview|--go" >&2; exit 2; }
cd ~/git-repos && set -a && source .env.jarvis_private && set +a
PY=/Users/matsunomasaharu2/selenium_env/venv/bin/python
exec "$PY" scripts/jarvis_ib_transfer_assist.py --bank kyoto "--$MODE" "${EXTRA[@]}"
