#!/bin/zsh
# FRIDAY / Jarvis 共用: 秘密を混ぜずに commit（任意で push）する。
#
# 使い方:
#   cd ~/git-repos
#   ./scripts/friday_git_commit.sh --message 'feat: …' -- path/to/file [path…]
#   ./scripts/friday_git_commit.sh --message 'feat: …' --push -- path/to/file
#   ./scripts/friday_git_commit.sh --status          # 予定ファイルの確認のみ
#   ./scripts/friday_git_commit.sh --dry-run --message '…' -- path…
#
# 既定: commit のみ（push しない）。--push で origin へ。
# 禁止: 秘密ファイル、force push、amend、main 以外への勝手なブランチ切替はしない。
set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO"

MSG=""
DO_PUSH=0
DRY_RUN=0
STATUS_ONLY=0
PATHS=()

usage() {
  sed -n '2,14p' "$0" | sed 's/^# \?//'
  exit "${1:-0}"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    -h|--help) usage 0 ;;
    --message|-m)
      MSG="${2:-}"; shift 2 ;;
    --push) DO_PUSH=1; shift ;;
    --dry-run) DRY_RUN=1; shift ;;
    --status) STATUS_ONLY=1; shift ;;
    --) shift; PATHS+=("$@"); break ;;
    -*)
      echo "[friday-git][ERROR] unknown option: $1" >&2
      usage 1 ;;
    *)
      PATHS+=("$1"); shift ;;
  esac
done

# パス名での秘密・危険パターン（マッチしたら拒否）
is_forbidden_path() {
  local p="$1"
  local base="${p:t}"
  case "$p" in
    .env.jarvis_private|.env|.env.*|*/.env|*/.env.*)
      [[ "$base" == *.example ]] && return 1
      [[ "$base" == *.example.* ]] && return 1
      return 0 ;;
  esac
  [[ "$base" == .env.jarvis_private ]] && return 0
  [[ "$base" == token.json || "$base" == token_*.json || "$base" == credentials.json || "$base" == credentials_*.json ]] && return 0
  [[ "$base" == *.pem || "$base" == *.key ]] && return 0
  [[ "$base" == *token*.json* || "$base" == *credentials*.json* ]] && return 0
  [[ "$base" == *.polluted_* || "$base" == *.bak_* || "$base" == *.expired ]] && return 0
  [[ "$p" == .jarvis_state/*.png || "$p" == .jarvis_state/*.txt || "$p" == .jarvis_state/*.pid ]] && return 0
  return 1
}

scan_paths_forbidden() {
  local p
  for p in "$@"; do
    if is_forbidden_path "$p"; then
      echo "[friday-git][ERROR] 秘密／除外パスのため拒否: $p" >&2
      return 1
    fi
  done
  return 0
}

# ステージ差分の簡易秘密スキャン（パターン定義そのものは除外）
scan_content_risk() {
  local diff hits
  diff="$(git diff --cached -U0 2>/dev/null || true)"
  [[ -z "$diff" ]] && return 0
  hits="$(
    print -r -- "$diff" | grep -E '^\+' | grep -Ev '^\+\+\+' | grep -E \
      -e 'sk-[A-Za-z0-9]{20,}' \
      -e 'AIza[0-9A-Za-z_-]{20,}' \
      -e '-----BEGIN (RSA |OPENSSH |EC )?PRIVATE KEY-----' \
      -e 'SERVICE_ROLE_KEY=[A-Za-z0-9_./+-]{20,}' \
      -e 'eyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{10,}' \
      || true
  )"
  if [[ -n "$hits" ]]; then
    echo "[friday-git][ERROR] 秘密っぽい文字列を検出。commit 中止:" >&2
    echo "$hits" | head -20 >&2
    return 1
  fi
  return 0
}

echo "[friday-git] repo=$REPO"
echo "[friday-git] branch=$(git rev-parse --abbrev-ref HEAD)"
echo "[friday-git] remote=$(git remote get-url origin 2>/dev/null || echo '(none)')"

if [[ $STATUS_ONLY -eq 1 ]]; then
  git status --short
  exit 0
fi

if [[ ${#PATHS[@]} -eq 0 ]]; then
  echo "[friday-git][ERROR] 対象パスを指定してください（-- path…）。全追加はしません。" >&2
  exit 1
fi

scan_paths_forbidden "${PATHS[@]}" || exit 1

MISSING=()
for p in "${PATHS[@]}"; do
  if [[ ! -e "$p" ]] && ! git ls-files --error-unmatch "$p" >/dev/null 2>&1; then
    # 削除コミット用: インデックスにあれば可
    if ! git ls-files --deleted -- "$p" | grep -qx "$p"; then
      MISSING+=("$p")
    fi
  fi
done
if [[ ${#MISSING[@]} -gt 0 ]]; then
  echo "[friday-git][ERROR] 存在しないパス:" >&2
  printf '  %s\n' "${MISSING[@]}" >&2
  exit 1
fi

if [[ -z "$MSG" ]]; then
  echo "[friday-git][ERROR] --message が必要です" >&2
  exit 1
fi

echo "[friday-git] paths (${#PATHS[@]}):"
printf '  %s\n' "${PATHS[@]}"

if [[ $DRY_RUN -eq 1 ]]; then
  echo "[friday-git] dry-run: git add / commit / push は実行しません"
  exit 0
fi

git add -- "${PATHS[@]}"
STAGED=("${(@f)$(git diff --cached --name-only)}")
if [[ ${#STAGED[@]} -eq 0 || -z "${STAGED[1]:-}" ]]; then
  echo "[friday-git][ERROR] ステージが空です（変更なし？）" >&2
  exit 1
fi
scan_paths_forbidden "${STAGED[@]}" || { git reset -q HEAD -- "${PATHS[@]}" 2>/dev/null || true; exit 1; }
scan_content_risk || { git reset -q HEAD -- "${PATHS[@]}" 2>/dev/null || true; exit 1; }

git commit -m "$(cat <<EOF
${MSG}

EOF
)"

HASH="$(git rev-parse --short HEAD)"
echo "[friday-git] committed $HASH"

if [[ $DO_PUSH -eq 1 ]]; then
  BRANCH="$(git rev-parse --abbrev-ref HEAD)"
  echo "[friday-git] pushing origin/$BRANCH …"
  git push origin "$BRANCH"
  echo "[friday-git] pushed"
else
  echo "[friday-git] push していません（GitHub 反映は --push）"
fi
