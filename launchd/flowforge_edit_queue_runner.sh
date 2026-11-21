#!/bin/zsh
# FlowForge 修正文の待ち箱の見張り: KeepAlive 常駐 → jarvis_flowforge_assistant_paste.py --queue-watch
# ChatGPT が MCP で置いた本人了承済みの修正文を、置き場の Chrome で FlowForge の AIアシスタントへ入力する。
# AI は呼ばない。詳細: docs/AIエージェントチーム/54b_FlowForge読取プロキシ_OpenAPI_20261106.md
set -euo pipefail
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PY="${HOME}/selenium_env/venv/bin/python"
export PATH="${HOME}/.local/bin:/opt/homebrew/bin:/usr/local/bin:${PATH}"

cd "$REPO_DIR"
# 待ち箱（Supabase）の2項目だけを、プログラムが .env.jarvis_private から読む。他の鍵は渡さない
exec "$PY" -u "${REPO_DIR}/scripts/jarvis_flowforge_assistant_paste.py" --queue-watch
