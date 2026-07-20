#!/usr/bin/env bash
# CHRLINE-Patch (.venv-patch) を GitHub 最新へ更新し、probe で検証。失敗時はバックアップから復旧。
#
# 使い方:
#   cd ~/git-repos && ./scripts/jarvis_chrline_update.sh
#   cd ~/git-repos && ./scripts/jarvis_chrline_update.sh --skip-probe
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
POC="$REPO/line_unofficial_poc"
VENV="$POC/.venv-patch"
PY="$VENV/bin/python"
PIP="$VENV/bin/pip"
RUN_PATCH="$POC/run_patch.sh"
BACKUP_ROOT="$REPO/.jarvis_state/chrline_patch_backups"
TMP_CLONE="/tmp/CHRLINE-Patch-jarvis-update"
SKIP_PROBE=0

for arg in "$@"; do
  case "$arg" in
    --skip-probe) SKIP_PROBE=1 ;;
    -h|--help)
      echo "Usage: $0 [--skip-probe]"
      exit 0
      ;;
  esac
done

if [[ ! -x "$PY" ]]; then
  echo "[jarvis_chrline_update] .venv-patch がありません: $PY" >&2
  echo "構築手順: docs/運用コマンド一覧.md の CHRLINE-Patch 節" >&2
  exit 1
fi

STAMP="$(date +%Y%m%d_%H%M%S)"
BACKUP_DIR="$BACKUP_ROOT/$STAMP"
SITE="$VENV/lib/python3.9/site-packages"
CHR_PKG="$SITE/CHRLINE"

echo "[jarvis_chrline_update] バックアップ: $BACKUP_DIR"
mkdir -p "$BACKUP_DIR"
cp -R "$CHR_PKG" "$BACKUP_DIR/CHRLINE"
for d in "$SITE"/chrline-*.dist-info; do
  [[ -d "$d" ]] && cp -R "$d" "$BACKUP_DIR/" || true
done

rollback() {
  echo "[jarvis_chrline_update] ロールバック中…" >&2
  rm -rf "$CHR_PKG"
  cp -R "$BACKUP_DIR/CHRLINE" "$CHR_PKG"
  for d in "$BACKUP_DIR"/chrline-*.dist-info; do
    [[ -d "$d" ]] && cp -R "$d" "$SITE/" || true
  done
  echo "[jarvis_chrline_update] ロールバック完了（$BACKUP_DIR）" >&2
}

trap 'echo "[jarvis_chrline_update] エラー。バックアップは $BACKUP_DIR にあります。" >&2' ERR

echo "[jarvis_chrline_update] pip install git+https://github.com/WEDeach/CHRLINE-Patch"
"$PIP" install -q --upgrade "git+https://github.com/WEDeach/CHRLINE-Patch"

echo "[jarvis_chrline_update] GitHub ソース上書き"
rm -rf "$TMP_CLONE"
git clone --depth 1 https://github.com/WEDeach/CHRLINE-Patch "$TMP_CLONE"
cp -R "$TMP_CLONE/CHRLINE" "$CHR_PKG"

# curve25519 .so が無ければ本番 venv から流用
if [[ ! -f "$SITE/axolotl_curve25519.cpython-39-darwin.so" ]] && [[ -f "$POC/.venv/lib/python3.9/site-packages/axolotl_curve25519.cpython-39-darwin.so" ]]; then
  cp "$POC/.venv/lib/python3.9/site-packages/axolotl_curve25519.cpython-39-darwin.so" "$SITE/"
  cp -R "$POC/.venv/lib/python3.9/site-packages/python_axolotl_curve25519-"*.dist-info "$SITE/" 2>/dev/null || true
fi

NEW_VER="$("$PY" -c "import importlib.metadata as m; print(m.version('CHRLINE'))")"
echo "[jarvis_chrline_update] インストール版: $NEW_VER"

if [[ "$SKIP_PROBE" -eq 1 ]]; then
  echo "[jarvis_chrline_update] --skip-probe: probe をスキップ"
else
  echo "[jarvis_chrline_update] Square probe 実行（保存トークン・QRなし）"
  set +e
  PROBE_OUT="$("$RUN_PATCH" chrline_patch_square_direct_probe.py 2>&1)"
  PROBE_RC=$?
  set -e
  echo "$PROBE_OUT" | grep -E "^# |child exit code|保存トークン|エラー" || true
  if [[ "$PROBE_RC" -ne 0 ]]; then
    echo "[jarvis_chrline_update] probe 失敗 (exit=$PROBE_RC) → ロールバック" >&2
    rollback
    exit "$PROBE_RC"
  fi
fi

echo "[jarvis_chrline_update] バージョン state 更新"
"$PY" "$REPO/scripts/jarvis_chrline_version_check.py" --force-upstream || true

echo "[jarvis_chrline_update] 完了: CHRLINE-Patch $NEW_VER"
