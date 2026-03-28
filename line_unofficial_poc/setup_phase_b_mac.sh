#!/usr/bin/env bash
# macOS（Apple Silicon 含む）で CHRLINE を入れる。
# python-axolotl-curve25519 が PyModuleDef の m_size に NULL を置いており、
# 新しい clang でビルド失敗する → patches で -1 に直してからビルドする。
#
# 使い方:
#   cd "$(dirname "$0")"
#   chmod +x setup_phase_b_mac.sh
#   ./setup_phase_b_mac.sh
#
# Python は Homebrew の 3.13+ を推奨: brew install python@3.13

set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
PATCH="$ROOT/patches/python-axolotl-curve25519-m_size.patch"
AX_VER="${AX_VER:-0.4.1.post2}"
CHR_VER="${CHR_VER:-2.5.14}"

if [[ ! -f "$PATCH" ]]; then
  echo "エラー: パッチが見つかりません: $PATCH" >&2
  exit 1
fi

pick_python() {
  if [[ -n "${PYTHON_BIN:-}" ]]; then
    echo "$PYTHON_BIN"
    return
  fi
  if command -v python3.13 >/dev/null 2>&1; then
    command -v python3.13
    return
  fi
  if command -v python3 >/dev/null 2>&1; then
    command -v python3
    return
  fi
  echo "エラー: python3.13 または python3 が見つかりません（brew install python@3.13 推奨）" >&2
  exit 1
}

PY="$(pick_python)"
echo "使用する Python: $PY ($("$PY" --version 2>&1))"

"$PY" -m venv "$ROOT/.venv"
# shellcheck source=/dev/null
source "$ROOT/.venv/bin/activate"
pip install -U pip setuptools wheel

TMP="$(mktemp -d)"
cleanup() { rm -rf "$TMP"; }
trap cleanup EXIT

echo "python-axolotl-curve25519==$AX_VER を取得してパッチ適用…"
pip download "python-axolotl-curve25519==$AX_VER" --no-binary :all: -d "$TMP"
tar -xzf "$TMP"/python-axolotl-curve25519-"$AX_VER".tar.gz -C "$TMP"
AX_DIR="$(ls -d "$TMP"/python-axolotl-curve25519-* | head -1)"
( cd "$AX_DIR" && patch -p0 <"$PATCH" )
pip install "$AX_DIR"

echo "CHRLINE==$CHR_VER をインストール…"
pip install "CHRLINE==$CHR_VER"

python -c "import CHRLINE; print('CHRLINE', CHRLINE.__version__, 'import OK')"

echo ""
echo "完了。.venv を有効化:  source $ROOT/.venv/bin/activate"
echo "次: PHASE_B_使い方.txt のログイン手順（CHRLINE の README / Wiki を参照）"
