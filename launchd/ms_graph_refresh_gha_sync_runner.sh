#!/bin/zsh
# OneDrive 書込で回転した MS_GRAPH_REFRESH_TOKEN を private と GHA Secrets へ反映（1時間ごと）。
# 回転が無ければ（~/.jarvis_state/ms_graph_new_refresh.env が無ければ）何もしない。
# トークンの値はログに出さない（sync_refresh は長さと指紋だけを出力）。失敗時だけ #ops へ1行。
set -uo pipefail
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
LOG_DIR="${HOME}/Library/Logs/jarvis_ms_graph_sync"
mkdir -p "$LOG_DIR"
LOG="${LOG_DIR}/sync.log"
PENDING="${HOME}/.jarvis_state/ms_graph_new_refresh.env"
STAMP="$(date '+%Y-%m-%d %H:%M:%S')"

if [[ ! -f "$PENDING" ]]; then
  echo "${STAMP} pending=なし（回転なし・何もしない）" >>"$LOG"
  exit 0
fi

cd "$REPO_DIR"
set -a
# shellcheck disable=SC1091
source "${REPO_DIR}/.env.jarvis_private"
set +a
PY="${HOME}/selenium_env/venv/bin/python"
[[ -x "$PY" ]] || PY="python3"

OUT="$("$PY" scripts/jarvis_ms_graph_sync_refresh.py --push-gha 2>&1)"
RC=$?
# 値が混ざらないよう末尾だけ・長い英数字列は伏せる
SAFE="$(printf '%s' "$OUT" | tail -c 300 | sed -E 's/[A-Za-z0-9._~+\/-]{40,}/[伏せ]/g' | tr '\n' ' ')"
echo "${STAMP} pending=あり exit=${RC} ${SAFE}" >>"$LOG"

if [[ $RC -ne 0 ]]; then
  "$PY" scripts/jarvis_slack_webhook_post.py --channel ops --signal off --no-fb-footer \
    --text "【OneDrive書込の鍵 GHA同期】🔴止まった｜件:—｜次:Macで jarvis_ms_graph_sync_refresh.py --push-gha（ログ ~/Library/Logs/jarvis_ms_graph_sync/sync.log）" \
    >>"$LOG" 2>&1 || true
fi
exit 0
