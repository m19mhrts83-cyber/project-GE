#!/bin/zsh
# Jarvis: iMessage/SMS 定常取込（20分ポーリング）
#   ~/Library/Messages/chat.db（読むだけ）→ 連絡先一覧の phones で照合 → 5.やり取り.md
#   = imessage_to_yoritoori.py（処理済み ROWID は ~/.cursor/imessage_processed.json）
# 要フルディスクアクセス: launchd 経由で chat.db を読むため、実行する python の実体に付与する。
# 失敗通知: 失敗が連続2回になったら Slack #ops に1回だけ。復旧したら1行。成功の毎回通知はしない。
# ログは件数と成否だけを確認に使う（本文・電話番号は書かない運用）。
set -uo pipefail
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PY="${JARVIS_PYTHON:-${HOME}/selenium_env/venv/bin/python}"
MANUAL_DIR="${REPO_DIR}/215_kamiooya/C1_cursor/1b_Cursorマニュアル"
LOG_DIR="${HOME}/Library/Logs/jarvis_imessage"
STATE="${LOG_DIR}/state.json"
mkdir -p "$LOG_DIR"
LOG="${LOG_DIR}/poll_$(date +%Y%m%d_%H%M%S).log"
LOCK_DIR="${LOG_DIR}/poll.lock"

acquired=0
if mkdir "$LOCK_DIR" 2>/dev/null; then
  acquired=1
elif [[ -d "$LOCK_DIR" ]]; then
  age=$(( $(date +%s) - $(stat -f %m "$LOCK_DIR" 2>/dev/null || echo 0) ))
  if (( age > 900 )); then
    rm -rf "$LOCK_DIR"
    mkdir "$LOCK_DIR" 2>/dev/null && acquired=1
  fi
fi
(( acquired )) || exit 0
trap 'rm -rf "$LOCK_DIR"' EXIT

# .env.jarvis_private（Slack Webhook 等）。壊れた行があっても落とさない
ENV_FILE="${REPO_DIR}/.env.jarvis_private"
[[ -f "$ENV_FILE" ]] || ENV_FILE="${HOME}/git-repos/.env.jarvis_private"
if [[ -f "$ENV_FILE" ]]; then
  set -a
  source "$ENV_FILE" 2>>"${LOG_DIR}/env_source.err.log"
  set +a
fi

cd "$MANUAL_DIR"
echo "# start $(date '+%Y-%m-%d %H:%M:%S %z') py=$(readlink -f "$PY" 2>/dev/null || echo "$PY")" >>"$LOG"
"$PY" -u imessage_to_yoritoori.py >>"$LOG" 2>&1
rc=$?
echo "# imessage exit=${rc} end $(date '+%Y-%m-%d %H:%M:%S %z')" >>"$LOG"

# 成功の判定は終了コードだけにしない: 「chat.db を開けました」が出ていること
ok=0
if (( rc == 0 )) && grep -q "chat.db を開けました" "$LOG"; then ok=1; fi

fails=0; notified=0
if [[ -f "$STATE" ]]; then
  fails="$(grep -oE '"consecutive_failures": [0-9]+' "$STATE" | grep -oE '[0-9]+$' || echo 0)"
  notified="$(grep -oE '"notified": [01]' "$STATE" | grep -oE '[01]$' || echo 0)"
fi
fails=${fails:-0}; notified=${notified:-0}

post() {
  "$PY" "${REPO_DIR}/scripts/jarvis_slack_webhook_post.py" --channel ops --signal off --no-fb-footer --text "$1" >/dev/null 2>&1 || true
}

if (( ok )); then
  if (( notified )); then
    post "【ops】iMessage 自動取り込みが復旧しました"
  fi
  printf '{"consecutive_failures": 0, "notified": 0}\n' >"$STATE"
else
  fails=$((fails + 1))
  why="$(grep -E 'エラー|Error|denied|unable' "$LOG" | tail -1 | cut -c1-120)"
  if (( fails >= 2 && ! notified )); then
    post "【ops】iMessage 自動取り込みが2回続けて失敗
原因: ${why:-不明}（chat.db が読めない場合はフルディスクアクセス）
ログ: ~/Library/Logs/jarvis_imessage/"
    notified=1
  fi
  printf '{"consecutive_failures": %d, "notified": %d}\n' "$fails" "$notified" >"$STATE"
fi

find "$LOG_DIR" -name 'poll_*.log' -mtime +14 -delete 2>/dev/null || true
exit 0
