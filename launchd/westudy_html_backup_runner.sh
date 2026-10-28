#!/bin/zsh
# WeStudy HTML バックアップ（毎週）。止まった回があれば続きから再開し、終わったらソースコード一式も 01_ソースコード へ書き出す
set -euo pipefail
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_DIR"
export PATH="$HOME/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"
if [[ "${WESTUDY_HTML_BACKUP_DISABLE:-0}" == "1" ]]; then
  echo "WESTUDY_HTML_BACKUP_DISABLE=1 → skip"
  exit 0
fi

# WeStudy の認証（週次取込と同じ .env）
ENV_FILE="${WESTUDY_ENV_FILE:-$HOME/Library/CloudStorage/OneDrive-個人用/215_神・大家さん倶楽部/C1_cursor/1c_神・大家さん倶楽部_AI推進/神・大家さん倶楽部情報Q&Aチャットボット/scripts/.env}"
emulate -R sh -c "set -a; . '${ENV_FILE}'; set +a"
PY="${JARVIS_PYTHON:-$HOME/selenium_env/venv/bin/python}"
WORK_ROOT="$REPO_DIR/.jarvis_state/westudy_html_backup"
mkdir -p "$WORK_ROOT"

# 二重起動しない（launchd の取りこぼし実行と手動実行が重なったとき）
LOCK="$WORK_ROOT/.running"
if ! mkdir "$LOCK" 2>/dev/null; then
  echo "already running ($LOCK)"
  exit 0
fi
trap 'rmdir "$LOCK" 2>/dev/null || true' EXIT

args=( --export-source )
# 途中で止まった回（_checkpoint.json が残っている作業フォルダ）があれば続きから
# (N/om) = 一致なしでもエラーにしない・フォルダだけ・新しい順
for d in "$WORK_ROOT"/2*(N/om); do
  if [[ -f "$d/_checkpoint.json" ]]; then
    args+=( --resume "${d:t}" )
    break
  fi
done

echo "start $(date '+%F %T') args=${args[*]}"
caffeinate -dimsu "$PY" "$REPO_DIR/scripts/westudy_html_backup.py" "${args[@]}"
echo "done $(date '+%F %T')"
