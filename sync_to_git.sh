#!/bin/zsh
# =============================================
# sync_to_git.sh
# クラウドフォルダの変更を git-repos に自動同期する
#
# 使い方:
#   手動実行:  ~/git-repos/sync_to_git.sh
#   自動監視:  ~/git-repos/sync_to_git.sh --watch
# =============================================

GIT_REPOS="$HOME/git-repos"

COMMON_EXCLUDES=(
  --exclude='.git'
  --exclude='.gitignore'
  --exclude='.venv'
  --exclude='**/.venv'
  --exclude='.cursor/projects'
  --exclude='.cursor/rules'
  --exclude='.obsidian'
  --exclude='.vscode'
  --exclude='.DS_Store'
)

# 同期ペア（元 → 先）を配列で定義
SYNC_SRCS=(
  "$HOME/Library/CloudStorage/OneDrive-個人用/215_神・大家さん倶楽部/"
  "$HOME/Library/CloudStorage/OneDrive-個人用/500_Obsidian/"
  "$HOME/Library/CloudStorage/OneDrive-個人用/300_AIリスキリング講座(助成金活用）/"
  "$HOME/Library/CloudStorage/GoogleDrive-m19m.hrts83@gmail.com/マイドライブ/DX互助会_共有フォルダ/"
)
SYNC_DSTS=(
  "$GIT_REPOS/215_kamiooya/"
  "$GIT_REPOS/500_obsidian/"
  "$GIT_REPOS/300_ai/"
  "$GIT_REPOS/dx_kyouyuu/"
)

RSYNC_TIMEOUT=90

sync_one() {
  local src="$1" dst="$2" name="$3"
  if [ ! -d "$src" ]; then
    echo "  ⚠ $name: 同期元が見つかりません（スキップ）"
    return
  fi
  echo "  → $name を同期中..."
  gtimeout ${RSYNC_TIMEOUT} rsync -a --ignore-errors \
    "${COMMON_EXCLUDES[@]}" \
    "$src" "$dst" 2>/dev/null
  local rc=$?
  if [ $rc -eq 124 ]; then
    echo "  ⚠ $name: ${RSYNC_TIMEOUT}秒で打ち切り（一部未同期の可能性あり）"
  elif [ $rc -ne 0 ]; then
    echo "  ⚠ $name: 一部エラーあり（同期可能な分は完了）"
  else
    echo "  ✓ $name: 同期完了"
  fi
}

sync_all() {
  echo "$(date '+%Y-%m-%d %H:%M:%S') 同期開始..."
  for i in {1..${#SYNC_SRCS[@]}}; do
    sync_one "${SYNC_SRCS[$i]}" "${SYNC_DSTS[$i]}" "$(basename "${SYNC_DSTS[$i]}")"
  done
  echo "$(date '+%Y-%m-%d %H:%M:%S') 同期完了"
  echo ""
}

if [ "${1:-}" = "--watch" ]; then
  echo "=== 自動同期モード（ファイル変更を監視中）==="
  echo "終了するには Ctrl+C を押してください"
  echo ""

  sync_all

  WATCH_DIRS=()
  for src in "${SYNC_SRCS[@]}"; do
    [ -d "$src" ] && WATCH_DIRS+=("$src")
  done

  fswatch -o --latency=10 \
    --exclude='\.git' --exclude='\.DS_Store' --exclude='\.venv' \
    --exclude='\.cursor/projects' --exclude='\.cursor/rules' \
    --exclude='\.obsidian' --exclude='\.vscode' \
    "${WATCH_DIRS[@]}" | while read -r _count; do
    sync_all
  done
else
  sync_all
  echo "ヒント: 自動監視するには  ~/git-repos/sync_to_git.sh --watch"
fi
