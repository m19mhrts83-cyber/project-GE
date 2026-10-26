#!/bin/zsh
# Claude Code（Code タブ）のワークツリーのうち、2週間放置で中身が安全なものだけ消す。
# セッション（会話）とブランチは残す。アーカイブはしない（「完了」運用のまま）。
#   既定はお試し（何も消さない）。--apply で実際に消す。
#   DAYS=14 で放置日数を変更。JARVIS_WORKTREE_CLEANUP_DISABLE=1 で停止。
# 消す条件（すべて満たすもの）:
#   1. 最後の活動から DAYS 日以上（会話ログ・git 操作・最終コミットの新しい方）
#   2. 未保存の変更なし（.agents/ は本体のコピーなので無視）
#   3. HEAD のコミットが origin/main か GitHub 上のブランチに残っている
set -uo pipefail

[[ "${JARVIS_WORKTREE_CLEANUP_DISABLE:-}" == "1" ]] && { echo "disabled"; exit 0; }

APPLY=0
[[ "${1:-}" == "--apply" ]] && APPLY=1
DAYS="${DAYS:-14}"
export PATH="$HOME/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"

# 本体（main のチェックアウト）を git worktree list の先頭から取る
SELF_DIR="$(cd "$(dirname "$0")/.." && pwd)"
REPO="$(git -C "$SELF_DIR" worktree list --porcelain | awk '/^worktree /{print substr($0,10); exit}')"
WT_ROOT="$REPO/.claude/worktrees"
PROJECTS="$HOME/.claude/projects"
NOW=$(date +%s)
LIMIT=$(( DAYS * 86400 ))

echo "== $(date '+%Y-%m-%d %H:%M') worktree cleanup (days=$DAYS apply=$APPLY)"
git -C "$REPO" fetch -q --prune origin 2>/dev/null || echo "warn: fetch failed（前回の情報で判定）"

removed=0
for wt in "$WT_ROOT"/*(N/); do
  name="${wt:t}"

  # 最後の活動（秒）
  last=0
  slug="${wt//[\/.]/-}"
  for f in "$PROJECTS/$slug"/*.jsonl(N); do
    t=$(stat -f %m "$f"); (( t > last )) && last=$t
  done
  gitdir="$(git -C "$wt" rev-parse --absolute-git-dir 2>/dev/null)"
  for f in "$gitdir/index" "$gitdir/logs/HEAD"; do
    [[ -e "$f" ]] || continue
    t=$(stat -f %m "$f"); (( t > last )) && last=$t
  done
  t=$(git -C "$wt" log -1 --format=%ct 2>/dev/null || echo 0); (( t > last )) && last=$t
  idle_days=$(( (NOW - last) / 86400 ))

  if (( NOW - last < LIMIT )); then
    echo "keep  $name: ${idle_days}日前に活動"
    continue
  fi

  changes="$(git -C "$wt" status --porcelain 2>/dev/null | grep -v '^?? .agents/$')"
  if [[ -n "$changes" ]]; then
    echo "keep  $name: 未保存の変更あり"
    continue
  fi

  head="$(git -C "$wt" rev-parse HEAD 2>/dev/null)"
  if ! git -C "$REPO" merge-base --is-ancestor "$head" origin/main 2>/dev/null \
     && [[ -z "$(git -C "$REPO" branch -r --contains "$head" 2>/dev/null)" ]]; then
    echo "keep  $name: GitHub に無いコミットあり"
    continue
  fi

  if (( APPLY )); then
    if git -C "$REPO" worktree remove --force "$wt"; then
      echo "rm    $name: ${idle_days}日放置"
      (( removed++ ))
    else
      echo "fail  $name"
    fi
  else
    echo "would $name: ${idle_days}日放置（--apply で削除）"
  fi
done

(( APPLY )) && git -C "$REPO" worktree prune
echo "done: removed=$removed"
