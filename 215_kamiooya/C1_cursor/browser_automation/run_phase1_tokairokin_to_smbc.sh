#!/bin/zsh
# Phase1: 東海労金 → 三井住友銀行 刈谷（Olive引落口座）
# プロトコル: Preview → Go / Terminal.app のみ / otp_channel=app_onetime_pw
# 正本: docs/KURASHIFT_送金アシスト_実務者設計_20260814.md
set -euo pipefail

RAIL_ID="tokairokin_smbc"
AMOUNT=232000
KEEP_FLOOR=121000
MODE=""
MONEY_OPS_ID=""
BALANCE=""

usage() {
  cat <<'EOF'
Usage (Terminal.app のみ — Cursor 統合ターミナル不可):
  ./run_phase1_tokairokin_to_smbc.sh --preview
  ./run_phase1_tokairokin_to_smbc.sh --go [--money-ops-id UUID] [--balance YEN]

  --preview   宛先マスク・金額・OTPチャネルを表示して終了（記帳しない）
  --go        ロック取得後に IB を開く（ワンタイムPWはユーザー入力）
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --preview) MODE=preview; shift ;;
    --go) MODE=go; shift ;;
    --money-ops-id) MONEY_OPS_ID="${2:-}"; shift 2 ;;
    --balance) BALANCE="${2:-}"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "unknown arg: $1" >&2; usage; exit 2 ;;
  esac
done

if [[ -z "$MODE" ]]; then
  usage
  exit 2
fi

cd ~/git-repos
set -a && source .env.jarvis_private && set +a

PY=/Users/matsunomasaharu2/selenium_env/venv/bin/python
export PYTHONPATH="$HOME/git-repos${PYTHONPATH:+:$PYTHONPATH}"

BRANCH="${PERSONAL_BANK_BRANCH_CODE:-}"
ACCT="${PERSONAL_BANK_ACCOUNT:-}"
DEST_MASK=$("$PY" -c "
from scripts.jarvis_transfer_audit import dest_mask
print(dest_mask('''$ACCT''', '''$BRANCH'''))
")
KEY=$("$PY" scripts/jarvis_transfer_audit.py key \
  --money-ops-id "${MONEY_OPS_ID:-noid}" \
  --rail-id "$RAIL_ID" \
  --amount "$AMOUNT" \
  --dest-mask "$DEST_MASK")

echo "=== 送金アシスト Preview ($RAIL_ID) ==="
echo "宛先: 三井住友銀行 刈谷(支店 ${BRANCH}) 普通 ${DEST_MASK}"
echo "金額: ${AMOUNT}円 / keep下限目安: ${KEEP_FLOOR}円"
echo "OTP: app_onetime_pw（スマホ「ワンタイムPW」— Jarvis は自動入力しません）"
echo "idempotency_key: $KEY"
echo "実行環境: Terminal.app 必須 / headless=false"

if [[ -n "$BALANCE" ]]; then
  "$PY" -c "
from scripts.jarvis_transfer_audit import assert_balance_keep
assert_balance_keep(int('''$BALANCE'''), $KEEP_FLOOR, $AMOUNT)
print('balance_keep: OK')
"
fi

"$PY" scripts/jarvis_transfer_audit.py append \
  --rail-id "$RAIL_ID" \
  --status previewed \
  --amount "$AMOUNT" \
  --dest-mask "$DEST_MASK" \
  --otp-channel app_onetime_pw \
  --money-ops-id "${MONEY_OPS_ID:-}"

if [[ "$MODE" == "preview" ]]; then
  echo "Preview のみ終了。実行するときは --go を付けて再実行してください。"
  exit 0
fi

echo ""
echo "Go: ロック取得 → IB 起動。OTP 画面でアプリのワンタイムPWを入力してください。"

"$PY" - <<PY
from scripts.jarvis_transfer_audit import TransferLock, append_audit
key = """$KEY"""
lock = TransferLock(key)
if not lock.acquire():
    raise SystemExit("lock_busy: 同一レールが実行中です")
append_audit({
    "rail_id": "$RAIL_ID",
    "status": "running",
    "amount_jpy": $AMOUNT,
    "dest_mask": "$DEST_MASK",
    "otp_channel": "app_onetime_pw",
    "otp_obtained": False,
    "money_ops_id": """${MONEY_OPS_ID}""" or None,
    "idempotency_key": key,
})
append_audit({
    "rail_id": "$RAIL_ID",
    "status": "waiting_user",
    "amount_jpy": $AMOUNT,
    "dest_mask": "$DEST_MASK",
    "otp_channel": "app_onetime_pw",
    "otp_obtained": False,
    "money_ops_id": """${MONEY_OPS_ID}""" or None,
    "error": "awaiting_app_onetime_pw",
})
# IB は別プロセスのため、短時間ロック後に解放（二重起動防止は監査＋運用）
lock.release()
print("lock_ok → waiting_user (app OTP)")
PY

cd ~/git-repos/215_kamiooya/C1_cursor/browser_automation
exec .venv/bin/python fetch_after_login.py tokairokin \
  --bank 0009 \
  --branch "$PERSONAL_BANK_BRANCH_CODE" \
  --account "$PERSONAL_BANK_ACCOUNT" \
  --amount "$AMOUNT"
