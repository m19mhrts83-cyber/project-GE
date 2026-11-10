#!/bin/zsh
# 神大家Q&A (3) 名簿の毎日取り込み（毎朝 6:00 JST、眠っていた日は起きたときに1回）。
# ~/git-repos の main は未コミットの変更で遅れることがあるので使わない。
# 名簿取り込み専用の worktree（origin/main を追う）を毎回 fetch → origin/main に切り替えてから実行する。
# ログには件数と成功・失敗だけを書く（名前・会員番号は kamiooya_roster_sync.py 自体が出さない）。
# 2回続けて失敗したら Slack #ops に1回知らせる（成功したら数え直し）。
#
# 実行中に worktree を切り替えるので、本文は関数にまとめて先に全部読み込ませる。
set -uo pipefail

main() {
  local MAIN_REPO="${HOME}/git-repos"
  local WT="${KAMIOOYA_ROSTER_WT:-${HOME}/.jarvis_worktrees/kamiooya-roster}"
  local LOG_DIR="${HOME}/Library/Logs/kamiooya_roster_sync"
  local STATE="${LOG_DIR}/state.json"
  local LOG="${LOG_DIR}/sync.log"
  local PY="${JARVIS_PYTHON:-${HOME}/selenium_env/venv/bin/python}"
  mkdir -p "$LOG_DIR"
  export PATH="${HOME}/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"

  [[ "${KAMIOOYA_ROSTER_SYNC_DISABLE:-0}" == "1" ]] && { echo "$(date '+%F %T') disabled" >>"$LOG"; return 0; }

  # 同じ日に成功済みなら何もしない（RunAtLoad と 6:00 の二重起動よけ）
  local today; today="$(TZ=Asia/Tokyo date +%F)"
  if [[ "${1:-}" != "--force" && -f "$STATE" ]] && grep -q "\"last_success_date\": \"${today}\"" "$STATE"; then
    echo "$(date '+%F %T') skip: 本日分は成功済み" >>"$LOG"
    return 0
  fi

  # 専用 worktree を用意して origin/main に合わせる
  if [[ ! -e "${WT}/.git" ]]; then
    mkdir -p "$(dirname "$WT")"
    git -C "$MAIN_REPO" worktree prune >/dev/null 2>&1 || true
    git -C "$MAIN_REPO" fetch -q origin main
    git -C "$MAIN_REPO" worktree add -q --detach "$WT" origin/main
  fi
  local tries=0 ok_git=0
  while (( tries < 4 )); do
    if git -C "$WT" fetch -q origin main && git -C "$WT" checkout -q -f --detach origin/main; then ok_git=1; break; fi
    tries=$((tries + 1)); sleep $((2 ** tries))
  done

  local rc=1 out="" attempt
  if (( ok_git )); then
    # Google 側の一時的な 5xx（Authentication backend unavailable など）に備えて最大3回
    for attempt in 1 2 3; do
      out="$(cd "$WT" && "$PY" scripts/kamiooya_roster_sync.py 2>&1 | grep -vE 'FutureWarning|warnings.warn' | tail -3)"
      if echo "$out" | grep -q "入れ替えました"; then rc=0; break; fi
      sleep $((attempt * 30))
    done
  else
    out="git fetch/checkout に失敗"
  fi

  local count; count="$(echo "$out" | grep -oE '会員番号 [0-9]+ 件' | head -1)"
  local head; head="$(git -C "$WT" rev-parse --short HEAD 2>/dev/null || echo '?')"
  local fails=0
  if [[ -f "$STATE" ]]; then
    fails="$(grep -oE '"consecutive_failures": [0-9]+' "$STATE" | grep -oE '[0-9]+$' || echo 0)"
  fi
  local last_ok=""
  [[ -f "$STATE" ]] && last_ok="$(grep -oE '"last_success_date": "[0-9-]*"' "$STATE" | grep -oE '[0-9]{4}-[0-9]{2}-[0-9]{2}' || true)"

  if (( rc == 0 )); then
    echo "$(date '+%F %T') OK ${count} (main ${head})" >>"$LOG"
    printf '{"last_success_date": "%s", "consecutive_failures": 0}\n' "$today" >"$STATE"
  else
    fails=$((fails + 1))
    # エラーの最後の1行だけ残す（名簿の中身は含まれない）
    local why; why="$(echo "$out" | tail -1 | cut -c1-160)"
    echo "$(date '+%F %T') FAIL #${fails} (main ${head}) ${why}" >>"$LOG"
    printf '{"last_success_date": "%s", "consecutive_failures": %d}\n' "$last_ok" "$fails" >"$STATE"
    if (( fails == 2 )); then
      emulate -R sh -c "set -a; . '${MAIN_REPO}/.env.jarvis_private'; set +a" 2>/dev/null || true
      "$PY" "${WT}/scripts/jarvis_slack_webhook_post.py" --channel ops --text \
"【ops】神大家 名簿の自動取り込みが2回続けて失敗
判定: 🔴 自動承認は前回の名簿のまま（最後の成功 ${last_ok:-不明}）
ログ: ~/Library/Logs/kamiooya_roster_sync/sync.log" >/dev/null 2>&1 || true
    fi
  fi
  return $rc
}

main "$@"
exit $?
