#!/usr/bin/env bash
# 前年度税込年収（給与・支払金額）を確定申告PDFから算出（ローン申込フォーム用）
# 正本: .env.jarvis_private の TAX_RETURN_*（固定の年収金額は保存しない）
set -euo pipefail

_JARVIS_TAX_SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
_JARVIS_TAX_PYTHON="${JARVIS_PYTHON:-/Users/matsunomasaharu2/selenium_env/venv/bin/python}"

# 環境変数が読み込まれている前提で ANNUAL_INCOME_* / TAX_RETURN_PDF_PATH を export
jarvis_export_annual_income() {
  local py="${_JARVIS_TAX_PYTHON}"
  local script="${_JARVIS_TAX_SCRIPT_DIR}/jarvis_tax_annual_income.py"
  if [[ ! -x "$py" ]] || [[ ! -f "$script" ]]; then
    unset ANNUAL_INCOME ANNUAL_INCOME_MANYEN ANNUAL_INCOME_GROSS_YEN TAX_RETURN_PDF_PATH
    return 1
  fi
  local out
  if ! out=$("$py" "$script" --export-shell 2>/dev/null); then
    unset ANNUAL_INCOME ANNUAL_INCOME_MANYEN ANNUAL_INCOME_GROSS_YEN TAX_RETURN_PDF_PATH
    return 1
  fi
  # shellcheck disable=SC1090
  eval "$out"
}
