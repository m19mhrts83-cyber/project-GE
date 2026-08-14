#!/bin/zsh
# Phase1: 住信SBIネット（本）→ SMBC刈谷 26,000円
# Terminal.app のみ。正本: docs/KURASHIFT_送金アシスト_実務者設計_20260814.md
set -euo pipefail
MODE=""
MONEY_OPS_ID=""
BALANCE_ARGS=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    --preview) MODE=preview; shift ;;
    --go) MODE=go; shift ;;
    --money-ops-id) MONEY_OPS_ID="${2:-}"; shift 2 ;;
    --balance) BALANCE_ARGS=(--balance "$2"); shift 2 ;;
    -h|--help)
      echo "Usage: $0 --preview | --go [--money-ops-id UUID] [--balance YEN]"
      exit 0
      ;;
    *) echo "unknown: $1" >&2; exit 2 ;;
  esac
done
[[ -n "$MODE" ]] || { echo "need --preview or --go" >&2; exit 2; }

cd ~/git-repos
set -a && source .env.jarvis_private && set +a
PY=/Users/matsunomasaharu2/selenium_env/venv/bin/python
ARGS=(scripts/jarvis_sbi_net_transfer.py --rail sbi_main_smbc "--$MODE" "${BALANCE_ARGS[@]}")
[[ -n "$MONEY_OPS_ID" ]] && ARGS+=(--money-ops-id "$MONEY_OPS_ID")
exec "$PY" "${ARGS[@]}"
