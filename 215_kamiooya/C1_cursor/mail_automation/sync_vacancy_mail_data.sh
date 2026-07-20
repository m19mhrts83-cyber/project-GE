#!/usr/bin/env bash
# OneDrive 正本 → git-repos 実行用ミラー（出先・Notion Cursor で git-repos のみ見えるとき用）
# 使い方: bash ~/git-repos/215_kamiooya/C1_cursor/mail_automation/sync_vacancy_mail_data.sh
#         bash .../sync_vacancy_mail_data.sh --md 260713_G1&G2_空室対策.md
set -euo pipefail

ONEDRIVE_ROOT="${HOME}/Library/CloudStorage/OneDrive-個人用/215_神・大家さん倶楽部"
SRC_XLSX="${ONEDRIVE_ROOT}/20_【空室対策】【修繕】【売却】/21_【空室対策】募集,ステージング,物件管理/★管理会社一覧.xlsx"
SRC_MD_DIR="${ONEDRIVE_ROOT}/C2_ルーティン作業/24_空室対策メール履歴"

DEST_DATA="${HOME}/git-repos/215_kamiooya/C1_cursor/mail_automation/data"
DEST_XLSX="${DEST_DATA}/管理会社一覧.xlsx"
DEST_MD_DIR="${HOME}/git-repos/215_kamiooya/C2_ルーティン作業/24_空室対策メール履歴"

mkdir -p "${DEST_DATA}" "${DEST_MD_DIR}"

if [[ ! -f "${SRC_XLSX}" ]]; then
  echo "エラー: OneDrive の管理会社一覧が見つかりません: ${SRC_XLSX}" >&2
  exit 1
fi

cp -f "${SRC_XLSX}" "${DEST_XLSX}"
echo "✓ Excel: ${DEST_XLSX} ($(wc -c < "${DEST_XLSX}" | tr -d ' ') bytes)"

MD_NAME=""
if [[ "${1:-}" == "--md" && -n "${2:-}" ]]; then
  MD_NAME="$2"
elif [[ -n "${1:-}" && "${1:-}" != "--md" ]]; then
  MD_NAME="$1"
fi

if [[ -n "${MD_NAME}" ]]; then
  SRC_MD="${SRC_MD_DIR}/${MD_NAME}"
  if [[ ! -f "${SRC_MD}" ]]; then
    echo "エラー: MD が見つかりません: ${SRC_MD}" >&2
    exit 1
  fi
  cp -f "${SRC_MD}" "${DEST_MD_DIR}/${MD_NAME}"
  echo "✓ MD: ${DEST_MD_DIR}/${MD_NAME}"
else
  # 直近の空室対策 MD を最大5件ミラー（既存上書き）
  count=0
  # shellcheck disable=SC2012
  for f in $(ls -1t "${SRC_MD_DIR}"/2*_空室対策*.md 2>/dev/null | head -5); do
    bn="$(basename "$f")"
    cp -f "$f" "${DEST_MD_DIR}/${bn}"
    echo "✓ MD: ${bn}"
    count=$((count + 1))
  done
  if [[ "$count" -eq 0 ]]; then
    echo "（MD 指定なし・直近ファイルもなし。Excel のみ同期）"
  fi
fi

echo "完了。出先送信の例:"
echo "  cd ~/git-repos/215_kamiooya/C1_cursor/mail_automation"
echo "  ~/selenium_env/venv/bin/python send_mail.py \\"
echo "    --md-file ~/git-repos/215_kamiooya/C2_ルーティン作業/24_空室対策メール履歴/<ファイル>.md \\"
echo "    --excel-file ~/git-repos/215_kamiooya/C1_cursor/mail_automation/data/管理会社一覧.xlsx \\"
echo "    --sheet-name G2 --yes"
