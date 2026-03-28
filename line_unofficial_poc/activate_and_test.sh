#!/usr/bin/env bash
# .venv を有効化して import テストのみ実行
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=/dev/null
source "$ROOT/.venv/bin/activate"
exec python "$ROOT/chrline_import_test.py"
