#!/bin/zsh
# Phase1 Wave1b: 住信SBIネット（本）→ SMBC刈谷 26,000円
# 最小ユーザー操作: アプリ承認／取れないOTPのみ。他は Jarvis。
# Terminal.app のみ。
set -euo pipefail
MODE=""
MONEY_OPS_ID=""
EXTRA=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    --preview) MODE=preview; shift ;;
    --go) MODE=go; shift ;;
    --resume) MODE=resume; shift ;;
    --execute) EXTRA+=(--execute); shift ;;
    --no-hold) EXTRA+=(--no-hold); shift ;;
    --money-ops-id) MONEY_OPS_ID="${2:-}"; shift 2 ;;
    --balance) EXTRA+=(--balance "$2"); shift 2 ;;
    -h|--help)
      cat <<'EOF'
Usage (Terminal.app):
  ./run_phase1_sbi_main_to_smbc.sh --preview
  ./run_phase1_sbi_main_to_smbc.sh --go [--execute] [--money-ops-id UUID]
  ./run_phase1_sbi_main_to_smbc.sh --resume [--execute]
あなた: アプリ承認 or 取れないOTPのみ / その他は Jarvis
EOF
      exit 0
      ;;
    *) echo "unknown: $1" >&2; exit 2 ;;
  esac
done
[[ -n "$MODE" ]] || { echo "need --preview|--go|--resume" >&2; exit 2; }
cd ~/git-repos
set -a && source .env.jarvis_private && set +a
PY=/Users/matsunomasaharu2/selenium_env/venv/bin/python
ARGS=(scripts/jarvis_sbi_net_transfer.py --rail sbi_main_smbc "--$MODE" "${EXTRA[@]}")
[[ -n "$MONEY_OPS_ID" ]] && ARGS+=(--money-ops-id "$MONEY_OPS_ID")
exec "$PY" "${ARGS[@]}"
