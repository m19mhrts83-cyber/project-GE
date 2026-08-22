#!/bin/zsh
# Jarvis Private バックアップ初回セットアップ（age 導入・鍵生成）
# 秘密鍵の中身は画面に出さない。EasyPass2 への控えはユーザーがファイルを開いて行う。
set -euo pipefail

AGE_DIR="${HOME}/.config/age"
BIN_DIR="${HOME}/bin"
PRIV="${AGE_DIR}/jarvis-private.key"
PUB="${AGE_DIR}/jarvis-private.pub"
REPO="$(cd "$(dirname "$0")/.." && pwd)"

mkdir -p "$AGE_DIR" "$BIN_DIR"

if [[ ! -x "${BIN_DIR}/age" ]]; then
  ARCH="$(uname -m)"
  case "$ARCH" in
    arm64) A=arm64 ;;
    x86_64) A=amd64 ;;
    *) echo "未対応アーキテクチャ: $ARCH"; exit 1 ;;
  esac
  VER="v1.2.1"
  TMP="$(mktemp -d)"
  echo "# downloading age ${VER} darwin-${A} → ${BIN_DIR}"
  curl -fsSL -o "${TMP}/age.tgz" \
    "https://github.com/FiloSottile/age/releases/download/${VER}/age-v1.2.1-darwin-${A}.tar.gz"
  tar -xzf "${TMP}/age.tgz" -C "$TMP"
  cp "${TMP}/age/age" "${TMP}/age/age-keygen" "$BIN_DIR/"
  chmod +x "${BIN_DIR}/age" "${BIN_DIR}/age-keygen"
  rm -rf "$TMP"
fi

AGE_KEYGEN="${BIN_DIR}/age-keygen"
[[ -x "$AGE_KEYGEN" ]] || AGE_KEYGEN="$(command -v age-keygen)"

if [[ ! -f "$PRIV" ]]; then
  echo "# generating ${PRIV} (contents not printed)"
  "$AGE_KEYGEN" -o "$PRIV"
  chmod 600 "$PRIV"
else
  echo "# existing private key kept: ${PRIV}"
fi

"$AGE_KEYGEN" -y "$PRIV" >"$PUB"
chmod 644 "$PUB"
echo "# public key written: ${PUB}"

cat <<EOF

✅ setup 完了

【必須・今すぐ】秘密鍵の緊急控え
1. EasyPass2 を開く
2. 新規項目（例タイトル: age jarvis-private.key 復号用）
3. 次のファイルを開き、全文をメモ欄へ貼付して保存:
   ${PRIV}
4. 貼付後、このターミナルやチャットに鍵を再掲しない

【バックアップ初回】
  ${HOME}/selenium_env/venv/bin/python ${REPO}/scripts/jarvis_private_backup.py --backup
  ${HOME}/selenium_env/venv/bin/python ${REPO}/scripts/jarvis_private_backup.py --status

【週次】
  ${REPO}/launchd/install_jarvis_private_backup_launchd.sh

EOF
