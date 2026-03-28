#!/usr/bin/env bash
# CHRLINE-PatchV2（k4zum4-sk/CHRLINE-PatchV2）を .venv に入れる。
# 先に ./setup_phase_b_mac.sh で venv とパッチ済み python-axolotl-curve25519 があること。
#
# 理由: PyPI の CHRLINE 2.5.14 は古く、QR ログインが LINE 側 403 になりやすい。
# フォーク 2.6.0b18 は DESKTOPWIN + useThrift 等の経路が README / test に沿っている。
#
# 上流に CHRLINE/utils/__init__.py が無く setuptools が utils を落とすため、
# クローン後に空の __init__.py を補う（git pull 後も再実行で復旧）。

set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
CLONE="$ROOT/chrline-patchv2"
REPO="https://github.com/k4zum4-sk/CHRLINE-PatchV2.git"

if [[ ! -f "$ROOT/.venv/bin/activate" ]]; then
  echo "エラー: .venv がありません。先に:  $ROOT/setup_phase_b_mac.sh" >&2
  exit 1
fi

if [[ ! -d "$CLONE/.git" ]]; then
  git clone --depth 1 "$REPO" "$CLONE"
else
  git -C "$CLONE" pull --ff-only || true
fi

UTIL_INIT="$CLONE/CHRLINE/utils/__init__.py"
if [[ ! -f "$UTIL_INIT" ]]; then
  printf '%s\n' '"""Package marker so setuptools includes CHRLINE.utils (local fix)."""' >"$UTIL_INIT"
fi

# shellcheck source=/dev/null
source "$ROOT/.venv/bin/activate"
pip uninstall -y CHRLINE 2>/dev/null || true
pip install -q rich pycryptodomex
pip install -q "$CLONE"

python -c "import CHRLINE; print('CHRLINE-PatchV2 import OK:', CHRLINE.__version__)"

echo ""
echo "QR ログイン試行:  source $ROOT/.venv/bin/activate"
echo "                  set -a && source $ROOT/.env && set +a"
echo "                  python $ROOT/chrline_qr_login_poc.py"
echo "元の PyPI 版に戻す:  pip uninstall -y CHRLINE && pip install 'CHRLINE==2.5.14'"
