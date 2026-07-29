#!/usr/bin/env bash
# OneDrive 正本 → git-repos 実行用ミラー
# 空室メール送信の標準手順: 本スクリプトで同期したあと、ローカル（ミラー）パスで send_mail.py する。
#
# 使い方:
#   bash ~/git-repos/215_kamiooya/C1_cursor/mail_automation/sync_vacancy_mail_data.sh
#   bash .../sync_vacancy_mail_data.sh --md 260721_G1&G2_空室対策.md
set -euo pipefail

ONEDRIVE_ROOT="${HOME}/Library/CloudStorage/OneDrive-個人用/215_神・大家さん倶楽部"
SRC_XLSX="${ONEDRIVE_ROOT}/20_【空室対策】【修繕】【売却】/21_【空室対策】募集,ステージング,物件管理/★管理会社一覧.xlsx"
SRC_MD_DIR="${ONEDRIVE_ROOT}/C2_ルーティン作業/24_空室対策メール履歴"

DEST_DATA="${HOME}/git-repos/215_kamiooya/C1_cursor/mail_automation/data"
DEST_XLSX="${DEST_DATA}/管理会社一覧.xlsx"
DEST_MD_DIR="${HOME}/git-repos/215_kamiooya/C2_ルーティン作業/24_空室対策メール履歴"

mkdir -p "${DEST_DATA}" "${DEST_MD_DIR}"

_file_stamp() {
  local p="$1"
  if [[ ! -f "$p" ]]; then
    echo "(missing)"
    return
  fi
  local sz ck mt
  sz="$(wc -c < "$p" | tr -d ' ')"
  ck="$(cksum < "$p" | awk '{print $1"/"$2}')"
  mt="$(stat -f '%Sm' -t '%Y-%m-%d %H:%M:%S' "$p" 2>/dev/null || true)"
  echo "${sz} bytes  cksum=${ck}  mtime=${mt}"
}

if [[ ! -f "${SRC_XLSX}" ]]; then
  echo "エラー: OneDrive の管理会社一覧が見つかりません: ${SRC_XLSX}" >&2
  echo "（OneDrive 未同期・オフラインの可能性）" >&2
  exit 1
fi

echo "📎 同期元（OneDrive 正本）"
echo "  Excel: ${SRC_XLSX}"
echo "         $(_file_stamp "${SRC_XLSX}")"

cp -f "${SRC_XLSX}" "${DEST_XLSX}"

if ! cmp -s "${SRC_XLSX}" "${DEST_XLSX}"; then
  echo "エラー: Excel コピー後に内容が一致しません（同期失敗の疑い）" >&2
  exit 1
fi

echo "✓ Excel → ローカルミラー"
echo "  ${DEST_XLSX}"
echo "  $(_file_stamp "${DEST_XLSX}")"
echo "  検証: cmp OK（OneDrive と一致）"

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
  if ! cmp -s "${SRC_MD}" "${DEST_MD_DIR}/${MD_NAME}"; then
    echo "エラー: MD コピー後に内容が一致しません: ${MD_NAME}" >&2
    exit 1
  fi
  echo "✓ MD → ローカルミラー: ${MD_NAME}（cmp OK）"
  echo "  $(_file_stamp "${DEST_MD_DIR}/${MD_NAME}")"
else
  # 直近の空室対策 MD を最大5件ミラー（既存上書き）
  count=0
  # shellcheck disable=SC2012
  for f in $(ls -1t "${SRC_MD_DIR}"/2*_空室対策*.md 2>/dev/null | head -5); do
    bn="$(basename "$f")"
    cp -f "$f" "${DEST_MD_DIR}/${bn}"
    if ! cmp -s "$f" "${DEST_MD_DIR}/${bn}"; then
      echo "エラー: MD コピー後に内容が一致しません: ${bn}" >&2
      exit 1
    fi
    echo "✓ MD: ${bn}（cmp OK）"
    count=$((count + 1))
  done
  if [[ "$count" -eq 0 ]]; then
    echo "（MD 指定なし・直近ファイルもなし。Excel のみ同期）"
  fi
fi

echo ""
echo "完了。送信はローカルミラーを指定（OneDrive 直読みはしない）:"
echo "  cd ~/git-repos/215_kamiooya/C1_cursor/mail_automation"
echo "  ~/selenium_env/venv/bin/python send_mail.py \\"
echo "    --md-file ~/git-repos/215_kamiooya/C2_ルーティン作業/24_空室対策メール履歴/<ファイル>.md \\"
echo "    --excel-file ~/git-repos/215_kamiooya/C1_cursor/mail_automation/data/管理会社一覧.xlsx \\"
echo "    --sheet-name G2 --yes"
