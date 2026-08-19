#!/bin/bash
# Cursor 用 Notion MCP。トークンは mcp.json に書かず .env.jarvis_private から読む。
set -euo pipefail
ENV_FILE="${JARVIS_PRIVATE_ENV:-$HOME/git-repos/.env.jarvis_private}"
if [[ ! -f "$ENV_FILE" ]]; then
  echo "jarvis_notion_mcp: $ENV_FILE がありません" >&2
  exit 1
fi
set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a
if [[ -z "${NOTION_API_TOKEN:-}" ]]; then
  echo "jarvis_notion_mcp: NOTION_API_TOKEN 未設定" >&2
  exit 1
fi
export NOTION_TOKEN="$NOTION_API_TOKEN"
NPX="${JARVIS_NPX:-/usr/local/bin/npx}"
if [[ ! -x "$NPX" ]]; then
  NPX="$(command -v npx)"
fi
exec "$NPX" -y @notionhq/notion-mcp-server "$@"
