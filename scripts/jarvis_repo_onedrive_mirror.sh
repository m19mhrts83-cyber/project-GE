#!/bin/zsh
# =============================================================
# jarvis_repo_onedrive_mirror.sh
# ~/git-repos → OneDrive 疎ミラー（.git なし・秘密除外）
#
# 方針（2026-09-19 Jarvis 合意）:
#   - コードの本線は GitHub（m19mhrts83-cyber/project-GE）。
#     本ミラーは OneDrive 上の「疎コピー」であり正ではない。
#   - 秘密は age（scripts/jarvis_private_backup.py）。
#     平文 .env は OneDrive に置かない。
#   - 既定は dry-run。--apply で本番。
#
# 対象の決め方:
#   git ls-files --cached --others --exclude-standard
#   → .gitignore を単一の正とする（node_modules / .next / .venv /
#     __pycache__ / .git / .DS_Store 等は自動で外れる）
#   さらに .gitignore をすり抜ける秘密の実体を明示除外する。
#
# rsync を使わない理由:
#   macOS 標準は openrsync で --from0 非対応、
#   --files-from と --delete の併用も効かない（実測）。
#   正確な dry-run 報告のため自前で比較・転送する。
#
# 使い方:
#   scripts/jarvis_repo_onedrive_mirror.sh                 # dry-run（報告のみ）
#   scripts/jarvis_repo_onedrive_mirror.sh --apply         # 本番
#   scripts/jarvis_repo_onedrive_mirror.sh --init --apply  # 初回（既存宛先を明示承認）
# =============================================================
set -euo pipefail

REPO_DIR="${HOME}/git-repos"
ONEDRIVE_ROOT="${HOME}/Library/CloudStorage/OneDrive-個人用"
DEST="${ONEDRIVE_ROOT}/999_ドキュメント/git-repos_code_mirror"
MARKER=".jarvis_repo_mirror"
SENTINEL="${ONEDRIVE_ROOT}/.849C9593-D756-4E56-8D6E-42412F2A707B"

APPLY=0
INIT=0

usage() {
  cat <<'EOF'
usage: jarvis_repo_onedrive_mirror.sh [--apply] [--init]

  (no option)  dry-run。転送予定・削除予定・除外ヒットを報告するだけ
  --apply      実際にミラーを更新する
  --init       既存の宛先にマーカーが無くても --apply を許可（初回のみ）
  -h, --help   このヘルプ
EOF
}

for arg in "$@"; do
  case "$arg" in
    --apply) APPLY=1 ;;
    --init)  INIT=1 ;;
    -h|--help) usage; exit 0 ;;
    *) print -u2 "[mirror][ERROR] unknown option: $arg"; usage; exit 2 ;;
  esac
done

die() { print -u2 "[mirror][ERROR] $*"; exit 1 }

# ---- 前提チェック（未マウント時に転送・削除しない）------------
[[ -d "${REPO_DIR}/.git" ]] || die "リポジトリが見つかりません: ${REPO_DIR}"
[[ -d "${ONEDRIVE_ROOT}" ]] || die "OneDrive が未マウントです: ${ONEDRIVE_ROOT}"
[[ -e "${SENTINEL}" ]]      || die "OneDrive のマウント検証に失敗（sentinel 無し）: ${ONEDRIVE_ROOT}"
[[ -d "${ONEDRIVE_ROOT}/999_ドキュメント" ]] || die "退避先の親がありません: 999_ドキュメント"

cd "$REPO_DIR"

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

# ---- 1. 対象リスト（.gitignore を正とする）--------------------
git ls-files -z --cached --others --exclude-standard > "$tmp/all.nul"
n_entries=$(tr -cd '\0' < "$tmp/all.nul" | wc -c | tr -d ' ')
tr '\0' '\n' < "$tmp/all.nul" > "$tmp/all.txt"
n_lines=$(wc -l < "$tmp/all.txt" | tr -d ' ')

[[ "$n_entries" == "$n_lines" ]] || die "ファイル名に改行を含むものがあります（安全のため中止）"
[[ "$n_entries" -gt 0 ]] || die "対象ファイルが 0 件です（削除事故防止のため中止）"

# ---- 2. 秘密の明示除外（.gitignore をすり抜ける実体がある）----
: > "$tmp/keep.txt"
: > "$tmp/excl.txt"
: > "$tmp/gone.txt"
typeset -A keep_set

while IFS= read -r f; do
  [[ -z "$f" ]] && continue
  b="${f:t}"
  lb="${b:l}"
  lf="${f:l}"
  cat=""

  if [[ "$lb" == ".env" || ( "$lb" == .env.* && "$lb" != *.example ) ]]; then
    cat="env"                       # 平文 .env（*.example は残す）
  elif [[ "$lf" == *token*.json* ]]; then
    cat="token"                     # token*.json / *.json.bak_* / *.polluted_* 込み
  elif [[ "$lf" == *credentials*.json* ]]; then
    cat="credentials"
  elif [[ "$lf" == *.pem || "$lf" == *.key ]]; then
    cat="key"
  elif [[ "$lf" == *.polluted_* || "$lf" == *.bak_* || "$lf" == *.expired ]]; then
    cat="junk"                      # 退避・汚染の残骸
  fi

  if [[ -n "$cat" ]]; then
    print -r -- "${cat}	${f}" >> "$tmp/excl.txt"
  elif [[ ! -e "${REPO_DIR}/${f}" && ! -L "${REPO_DIR}/${f}" ]]; then
    # index にはあるが作業ツリーに実体が無い（削除済み・壊れたリンク）
    print -r -- "$f" >> "$tmp/gone.txt"
  else
    print -r -- "$f" >> "$tmp/keep.txt"
    keep_set["$f"]=1
  fi
done < "$tmp/all.txt"

n_keep=$(wc -l < "$tmp/keep.txt" | tr -d ' ')
[[ "$n_keep" -gt 0 ]] || die "除外後にファイルが 0 件です（削除事故防止のため中止）"

# ---- 3. 差分判定（size + mtime）-------------------------------
typeset -i n_new=0 n_upd=0 n_same=0 bytes_copy=0 bytes_total=0
: > "$tmp/new.txt"
: > "$tmp/upd.txt"

while IFS= read -r f; do
  src="${REPO_DIR}/${f}"
  dst="${DEST}/${f}"
  sstat="$(stat -f '%z %m' "$src" 2>/dev/null || print '0 0')"
  sz="${sstat%% *}"
  bytes_total=$((bytes_total + sz))

  if [[ ! -e "$dst" && ! -L "$dst" ]]; then
    n_new+=1
    bytes_copy=$((bytes_copy + sz))
    print -r -- "$f" >> "$tmp/new.txt"
  elif [[ "$sstat" != "$(stat -f '%z %m' "$dst" 2>/dev/null || print '')" ]]; then
    n_upd+=1
    bytes_copy=$((bytes_copy + sz))
    print -r -- "$f" >> "$tmp/upd.txt"
  else
    n_same+=1
  fi
done < "$tmp/keep.txt"

# ---- 4. 削除予定（ミラーなので宛先の余剰は消す）---------------
: > "$tmp/del.txt"
if [[ -d "$DEST" ]]; then
  while IFS= read -r p; do
    [[ -z "$p" ]] && continue
    rel="${p#${DEST}/}"
    [[ "$rel" == "$MARKER" ]] && continue
    # 添字は必ずクォート（zsh は非クォート添字をグロブ展開してしまう）
    if [[ -z "${keep_set["$rel"]:-}" ]]; then
      print -r -- "$rel" >> "$tmp/del.txt"
    fi
  done < <(find "$DEST" -type f 2>/dev/null)
fi
n_del=$(wc -l < "$tmp/del.txt" | tr -d ' ')

# ---- 5. 宛先ガード（他人のフォルダを消さない）-----------------
if [[ "$APPLY" -eq 1 && "$INIT" -eq 0 && -d "$DEST" && -n "$(ls -A "$DEST" 2>/dev/null)" && ! -e "${DEST}/${MARKER}" ]]; then
  die "宛先が既存かつマーカー ${MARKER} がありません。初回は --init を明示してください"
fi

# ---- 6. 報告 --------------------------------------------------
hr() { awk -v b="$1" 'BEGIN{ if (b>=1073741824) printf "%.1f GB", b/1073741824; else if (b>=1048576) printf "%.1f MB", b/1048576; else printf "%.1f KB", b/1024 }'; }
n_excl=$(wc -l < "$tmp/excl.txt" | tr -d ' ')
n_gone=$(wc -l < "$tmp/gone.txt" | tr -d ' ')

print -- "[mirror] source   : ${REPO_DIR}"
print -- "[mirror] dest     : ${DEST}"
if [[ "$APPLY" -eq 1 ]]; then print -- "[mirror] mode     : APPLY"; else print -- "[mirror] mode     : DRY-RUN（--apply で本番）"; fi
print -- "[mirror] 対象      : ${n_keep} ファイル / $(hr "$bytes_total")"
print -- "[mirror] 除外      : ${n_excl} 件"
if [[ "$n_excl" -gt 0 ]]; then
  awk -F'\t' '{c[$1]++} END{for (k in c) printf "           %-12s %d\n", k, c[k]}' "$tmp/excl.txt" | sort
  print -- "[mirror] 除外例    :"
  awk -F'\t' '{printf "           [%s] %s\n", $1, $2}' "$tmp/excl.txt" | head -8
fi
if [[ "$n_gone" -gt 0 ]]; then
  print -- "[mirror] 実体なし  : ${n_gone} 件（index にあるが作業ツリーに無い）"
  sed 's/^/           ? /' "$tmp/gone.txt" | head -5
fi
print -- "[mirror] 差分      : 新規 ${n_new} / 更新 ${n_upd} / 同一 ${n_same}"
print -- "[mirror] 転送予定  : $((n_new + n_upd)) ファイル / $(hr "$bytes_copy")"
print -- "[mirror] 削除予定  : ${n_del}"
if [[ "$n_del" -gt 0 ]]; then
  sed 's/^/           - /' "$tmp/del.txt" | head -10
fi

if [[ "$APPLY" -eq 0 ]]; then
  print -- "[mirror] 結果      : dry-run のため未変更"
  exit 0
fi

# ---- 7. 適用 --------------------------------------------------
mkdir -p "$DEST"
while IFS= read -r f; do
  mkdir -p "${DEST}/${f:h}"
  cp -pP "${REPO_DIR}/${f}" "${DEST}/${f}"   # -P: シンボリックリンクはリンクのまま複製

done < <(cat "$tmp/new.txt" "$tmp/upd.txt")

while IFS= read -r rel; do
  [[ -z "$rel" ]] && continue
  rm -f "${DEST}/${rel}"
done < "$tmp/del.txt"

find "$DEST" -type d -empty -delete 2>/dev/null || true

cat > "${DEST}/${MARKER}" <<EOF
Jarvis repo mirror (sparse, no .git)
source : ${REPO_DIR}
updated: $(date '+%Y-%m-%d %H:%M:%S %z')
files  : ${n_keep}
note   : コードの正は GitHub。秘密は age。ここは疎コピー。
EOF

print -- "[mirror] 結果      : 適用完了（新規 ${n_new} / 更新 ${n_upd} / 削除 ${n_del}）"
