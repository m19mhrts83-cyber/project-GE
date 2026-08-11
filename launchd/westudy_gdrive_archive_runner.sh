#!/bin/zsh
# WeStudy 自分用アーカイブ（admin Drive・本文＋添付）の週次更新。
# GHA の CSV→Supabase/Raimo とは別。画像は CI に載せない。
set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PY="${HOME}/selenium_env/venv/bin/python"
SCRAPER="${REPO_DIR}/ProgramCode/alfred_python/westudy_forum_all.py"
DRIVE="${HOME}/Library/CloudStorage/GoogleDrive-admin@livingsupport-matsu.co.jp/マイドライブ/215_神大家_WeStudyスクレイプ"
OUT="${DRIVE}/runs/archive"
STATE_DIR="${DRIVE}/state"
LOG_DIR="${HOME}/Library/Logs/jarvis_westudy_gdrive"
STATE_JSON="${REPO_DIR}/.jarvis_state/westudy_gdrive_weekly.json"
ENV_ONEDRIVE="${HOME}/Library/CloudStorage/OneDrive-個人用/215_神・大家さん倶楽部/C1_cursor/1c_神・大家さん倶楽部_AI推進/神・大家さん倶楽部情報Q&Aチャットボット/scripts/.env"
ENV_REPO="${REPO_DIR}/215_kamiooya/C1_cursor/1c_神・大家さん倶楽部_AI推進/神・大家さん倶楽部情報Q&Aチャットボット/scripts/.env"

mkdir -p "$LOG_DIR" "${REPO_DIR}/.jarvis_state" "$OUT" "$STATE_DIR"
STAMP="$(date +%Y%m%d_%H%M%S)"
LOG="${LOG_DIR}/archive_${STAMP}.log"

write_state() {
  local started="$1" finished="$2" exitc="$3"
  /usr/bin/python3 - "$STATE_JSON" "$started" "$finished" "$exitc" "$OUT" <<'PY'
import json, sys
from pathlib import Path
path, started, finished, exitc, out = sys.argv[1:6]
p = Path(path)
data = {}
if p.is_file():
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        data = {}
from datetime import datetime
from zoneinfo import ZoneInfo
now = datetime.now(ZoneInfo("Asia/Tokyo")).strftime("%Y-%m-%dT%H:%M:%S%z")
data.update({
    "last_started_at": started or data.get("last_started_at"),
    "last_finished_at": finished or None,
    "last_exit": int(exitc) if exitc != "" else data.get("last_exit"),
    "last_output": out,
    "updated_at": now,
})
if exitc != "":
    try:
        code = int(exitc)
    except ValueError:
        code = 1
    if code == 0:
        data["last_ok"] = True
        data["last_success_at"] = finished or now
        data["last_error"] = None
    else:
        data["last_ok"] = False
        data["last_error"] = f"exit={code}"
        data["last_error_at"] = finished or now
p.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
PY
}

if [[ "${JARVIS_WESTUDY_GDRIVE_WEEKLY_DISABLE:-}" == "1" ]]; then
  echo "# skip disabled $(date '+%Y-%m-%d %H:%M:%S')" >>"$LOG"
  exit 0
fi

if pgrep -f 'westudy_forum_all.py' >/dev/null 2>&1; then
  echo "# skip already running $(date '+%Y-%m-%d %H:%M:%S')" >>"$LOG"
  exit 0
fi

if [[ ! -d "$DRIVE" ]]; then
  echo "# Drive 未マウント: $DRIVE" >>"$LOG"
  write_state "$(date '+%Y-%m-%dT%H:%M:%S+09:00')" "$(date '+%Y-%m-%dT%H:%M:%S+09:00')" 2
  exit 2
fi

if [[ -f "$ENV_ONEDRIVE" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$ENV_ONEDRIVE"
  set +a
elif [[ -f "$ENV_REPO" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$ENV_REPO"
  set +a
fi

if [[ -z "${WESTUDY_USER:-}" || -z "${WESTUDY_PASS:-}" ]]; then
  echo "# WESTUDY_USER/PASS なし" >>"$LOG"
  write_state "$(date '+%Y-%m-%dT%H:%M:%S+09:00')" "$(date '+%Y-%m-%dT%H:%M:%S+09:00')" 2
  exit 2
fi

STARTED="$(date '+%Y-%m-%dT%H:%M:%S+09:00')"
write_state "$STARTED" "" ""

set +e
{
  echo "# start $(date '+%Y-%m-%d %H:%M:%S %z')"
  echo "# out=$OUT"
  cd "$REPO_DIR"
  # 既存ファイルはスキップ。新規コメントの画像を拾うため --force
  /usr/bin/caffeinate -dimsu "$PY" -u "$SCRAPER" \
    --force --save-attachments \
    --output-root "$OUT" \
    --state-dir "$STATE_DIR"
  echo "# end exit=$?"
} >>"$LOG" 2>&1
EC=$?
set -e
write_state "$STARTED" "$(date '+%Y-%m-%dT%H:%M:%S+09:00')" "$EC"
exit "$EC"
