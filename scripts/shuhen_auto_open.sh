#!/usr/bin/env bash
# 周辺MAP 単独Web（自分用）— サーバ起動＋ブラウザ表示
# 用法:
#   ./scripts/shuhen_auto_open.sh
#   ./scripts/shuhen_auto_open.sh --caramel
#   NAME=… ADDRESS=… ./scripts/shuhen_auto_open.sh
#
# サーバは start_new_session で起動し、親シェル終了に巻き込まれない。
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
PY="${SHUHEN_PYTHON:-/Users/matsunomasaharu2/selenium_env/venv/bin/python}"
PORT="${SHUHEN_AUTO_PORT:-8770}"
URL="http://127.0.0.1:${PORT}/shuhen-auto.html"
LOG="${SHUHEN_AUTO_LOG:-/tmp/shuhen_auto_server.log}"

if [[ -f .env.jarvis_private ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env.jarvis_private
  set +a
fi

QS=""
if [[ "${1:-}" == "--caramel" ]]; then
  QS="?name=$(python3 -c 'import urllib.parse; print(urllib.parse.quote("キャラメル"))')&address=$(python3 -c 'import urllib.parse; print(urllib.parse.quote("愛知県名古屋市緑区文久山418"))')&target=$(python3 -c 'import urllib.parse; print(urllib.parse.quote("ファミリー"))')&count=15"
elif [[ -n "${NAME:-}" && -n "${ADDRESS:-}" ]]; then
  QS="?name=$(python3 -c "import urllib.parse,os; print(urllib.parse.quote(os.environ['NAME']))")&address=$(python3 -c "import urllib.parse,os; print(urllib.parse.quote(os.environ['ADDRESS']))")"
  [[ -n "${TARGET:-}" ]] && QS+="&target=$(python3 -c "import urllib.parse,os; print(urllib.parse.quote(os.environ['TARGET']))")"
  [[ -n "${COUNT:-}" ]] && QS+="&count=${COUNT}"
fi

health_ok() {
  curl -sf --max-time 2 "http://127.0.0.1:${PORT}/api/health" >/dev/null 2>&1
}

start_server() {
  echo "Starting shuhen_auto_server on :${PORT} …"
  export SHUHEN_AUTO_PORT="$PORT"
  # 新しいセッションで起動（Cursor/シェル終了で SIGTERM されない）
  "$PY" - <<'PY'
import os, subprocess, sys
from pathlib import Path
root = Path(os.environ["ROOT"])
py = os.environ["PY"]
log = os.environ["LOG"]
env = os.environ.copy()
env["SHUHEN_AUTO_PORT"] = os.environ["PORT"]
logf = open(log, "a", buffering=1)
subprocess.Popen(
    [py, str(root / "scripts" / "shuhen_auto_server.py")],
    cwd=str(root),
    env=env,
    stdout=logf,
    stderr=subprocess.STDOUT,
    start_new_session=True,
    close_fds=True,
)
print("spawned", flush=True)
PY
  for _ in $(seq 1 40); do
    health_ok && return 0
    sleep 0.25
  done
  echo "ERROR: server did not become healthy. See ${LOG}" >&2
  tail -30 "$LOG" >&2 || true
  return 1
}

export ROOT PY PORT LOG
if ! health_ok; then
  start_server
fi

echo "API: $(curl -sf --max-time 2 "http://127.0.0.1:${PORT}/api/health")"
open "${URL}${QS}"
echo "Opened ${URL}${QS}"
