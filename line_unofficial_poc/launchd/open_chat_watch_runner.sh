#!/bin/zsh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$REPO_DIR"

if [[ -f ".env" ]]; then
  set -a
  source ".env"
  set +a
fi

ROUTES_YAML="${LINE_OPEN_CHAT_ROUTES_YAML:-$REPO_DIR/open_chat_routes.yaml}"

if [[ ! -f "$ROUTES_YAML" ]]; then
  echo "[watch] routes yaml が見つかりません: $ROUTES_YAML" >&2
  exit 1
fi

if [[ ! -x "$REPO_DIR/.venv/bin/python" ]]; then
  echo "[watch] Python 仮想環境が見つかりません: $REPO_DIR/.venv/bin/python" >&2
  exit 1
fi

exec "$REPO_DIR/.venv/bin/python" "$REPO_DIR/chrline_open_chat_realtime_watch.py" --routes-yaml "$ROUTES_YAML"
