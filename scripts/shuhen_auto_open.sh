#!/usr/bin/env bash
# 周辺MAP 単独Web（自分用）— サーバ起動＋ブラウザ表示
# 用法:
#   ./scripts/shuhen_auto_open.sh
#   ./scripts/shuhen_auto_open.sh --caramel
#   NAME=… ADDRESS=… ./scripts/shuhen_auto_open.sh
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
PY="${SHUHEN_PYTHON:-/Users/matsunomasaharu2/selenium_env/venv/bin/python}"
PORT="${SHUHEN_AUTO_PORT:-8770}"
URL="http://127.0.0.1:${PORT}/shuhen-auto.html"

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
  curl -sf "http://127.0.0.1:${PORT}/api/health" >/dev/null 2>&1
}

if ! health_ok; then
  echo "Starting shuhen_auto_server on :${PORT} …"
  export SHUHEN_AUTO_PORT="$PORT"
  nohup "$PY" scripts/shuhen_auto_server.py >>/tmp/shuhen_auto_server.log 2>&1 &
  for _ in $(seq 1 30); do
    health_ok && break
    sleep 0.2
  done
  if ! health_ok; then
    echo "ERROR: server did not become healthy. See /tmp/shuhen_auto_server.log" >&2
    exit 1
  fi
fi

echo "API: $(curl -sf "http://127.0.0.1:${PORT}/api/health")"
open "${URL}${QS}"
echo "Opened ${URL}${QS}"
