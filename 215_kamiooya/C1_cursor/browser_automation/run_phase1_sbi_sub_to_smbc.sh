#!/bin/zsh
# Phase1 Wave1b: 第一生命NEOBANK（副）→ SMBC刈谷 161,000円
# ことら分割: --chunk 0 → 100,000 / --chunk 1 → 61,000
# Terminal.app のみ。
set -euo pipefail
MODE=""
MONEY_OPS_ID=""
CHUNK=0
EXTRA=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    --preview) MODE=preview; shift ;;
    --go) MODE=go; shift ;;
    --resume) MODE=resume; shift ;;
    --execute) EXTRA+=(--execute); shift ;;
    --no-hold) EXTRA+=(--no-hold); shift ;;
    --chunk) CHUNK="${2:-0}"; shift 2 ;;
    --money-ops-id) MONEY_OPS_ID="${2:-}"; shift 2 ;;
    --balance) EXTRA+=(--balance "$2"); shift 2 ;;
    -h|--help)
      cat <<'EOF'
Usage (Terminal.app):
  ./run_phase1_sbi_sub_to_smbc.sh --preview
  ./run_phase1_sbi_sub_to_smbc.sh --go --chunk 0 --execute   # 100,000
  ./run_phase1_sbi_sub_to_smbc.sh --go --chunk 1 --execute   # 61,000
  ./run_phase1_sbi_sub_to_smbc.sh --resume --execute
あなた: アプリ承認 or 取れないOTPのみ
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
ARGS=(scripts/jarvis_sbi_net_transfer.py --rail sbi_sub_smbc "--$MODE" --chunk "$CHUNK" "${EXTRA[@]}")
[[ -n "$MONEY_OPS_ID" ]] && ARGS+=(--money-ops-id "$MONEY_OPS_ID")
exec "$PY" "${ARGS[@]}"
