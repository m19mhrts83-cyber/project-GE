#!/bin/zsh
# Wave2: エアウォレット→SMBC（アプリ中心・SMS OTP自動・初回着金ゲート）
set -euo pipefail
MODE=""
EXTRA=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    --preview) MODE=preview; shift ;;
    --go) MODE=go; EXTRA+=(--open); shift ;;
    --mark-arrival-proven) MODE=mark; shift ;;
    --complete) MODE=complete; shift ;;
    --fetch-sms-otp) MODE=sms; shift ;;
    --money-ops-id) EXTRA+=(--money-ops-id "$2"); shift 2 ;;
    --amount) EXTRA+=(--amount "$2"); shift 2 ;;
    --balance) EXTRA+=(--balance "$2"); shift 2 ;;
    --note) EXTRA+=(--note "$2"); shift 2 ;;
    --evidence) EXTRA+=(--evidence "$2"); shift 2 ;;
    --allow-unproven) EXTRA+=(--allow-unproven); shift ;;
    --no-poll-sms) EXTRA+=(--no-poll-sms); shift ;;
    -h|--help)
      echo "Usage: $0 --preview|--go|--mark-arrival-proven|--complete|--fetch-sms-otp"
      exit 0 ;;
    *) echo "unknown $1" >&2; exit 2 ;;
  esac
done
[[ -n "$MODE" ]] || { echo "need mode" >&2; exit 2; }
cd ~/git-repos && set -a && source .env.jarvis_private && set +a
PY=/Users/matsunomasaharu2/selenium_env/venv/bin/python
case "$MODE" in
  preview) exec "$PY" scripts/jarvis_airwallet_transfer.py --preview "${EXTRA[@]}" ;;
  go) exec "$PY" scripts/jarvis_airwallet_transfer.py --go "${EXTRA[@]}" ;;
  mark) exec "$PY" scripts/jarvis_airwallet_transfer.py --mark-arrival-proven "${EXTRA[@]}" ;;
  complete) exec "$PY" scripts/jarvis_airwallet_transfer.py --complete "${EXTRA[@]}" ;;
  sms) exec "$PY" scripts/jarvis_airwallet_transfer.py --fetch-sms-otp ;;
esac
