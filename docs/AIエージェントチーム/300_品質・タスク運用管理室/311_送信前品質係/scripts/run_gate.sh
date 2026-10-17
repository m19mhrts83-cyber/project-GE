#!/usr/bin/env bash
# 311 薄いラッパ。本線は ~/git-repos/scripts/jarvis_send_gate_311.py
set -euo pipefail
REPO="${HOME}/git-repos"
PY="${HOME}/selenium_env/venv/bin/python"
cd "$REPO"
set -a
# shellcheck disable=SC1091
source "$REPO/.env.jarvis_private"
set +a
exec "$PY" "$REPO/scripts/jarvis_send_gate_311.py" "$@"
