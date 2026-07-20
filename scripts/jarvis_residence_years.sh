#!/usr/bin/env bash
# 居住年数を「建築年月／入居年月」から算出（ローン申込フォーム用）
# 正本: .env.jarvis_private の HOME_BUILT_YM（入居が異なるときは HOME_OCCUPIED_SINCE）
set -euo pipefail

# 基準年月 YYYY-MM → その月を含めて何年居住したか（満年数、1年未満は1）
jarvis_residence_years() {
  local ym="${1:-}"
  local ref_date="${2:-}"

  if [[ -z "$ym" || ! "$ym" =~ ^[0-9]{4}-[0-9]{2}$ ]]; then
    echo ""
    return 1
  fi

  local start_y start_m
  start_y=${ym%-*}
  start_m=${ym#*-}
  start_m=$((10#$start_m))

  local ref_y ref_m
  if [[ -n "$ref_date" ]]; then
    ref_y=${ref_date:0:4}
    ref_m=${ref_date:5:2}
    ref_m=$((10#$ref_m))
  else
    ref_y=$(date +%Y)
    ref_m=$((10#$(date +%m)))
  fi

  local years=$((ref_y - start_y))
  if (( ref_m < start_m )); then
    years=$((years - 1))
  fi
  if (( years < 1 )); then
    years=1
  fi
  echo "$years"
}

# 環境変数が読み込まれている前提で RESIDENCE_YEARS を算出して export
jarvis_export_residence_years() {
  local base="${HOME_OCCUPIED_SINCE:-${HOME_BUILT_YM:-}}"
  local as_of="${RESIDENCE_YEARS_AS_OF:-}"
  if [[ -z "$base" ]]; then
    unset RESIDENCE_YEARS
    return 0
  fi
  RESIDENCE_YEARS=$(jarvis_residence_years "$base" "$as_of")
  export RESIDENCE_YEARS
}

# 入社年月 EMPLOYMENT_START_YM → 勤続年数（満年数）
jarvis_export_employment_years() {
  local base="${EMPLOYMENT_START_YM:-}"
  local as_of="${EMPLOYMENT_YEARS_AS_OF:-}"
  if [[ -z "$base" ]]; then
    unset EMPLOYMENT_YEARS
    return 0
  fi
  EMPLOYMENT_YEARS=$(jarvis_residence_years "$base" "$as_of")
  export EMPLOYMENT_YEARS
}
