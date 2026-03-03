#!/bin/bash
# .env と config_nichinoken.yaml を Git の追跡から外す（ファイルは削除しない）。
# リポジトリルート（215_神・大家さん倶楽部）で実行してください。
# 例: cd "/path/to/215_神・大家さん倶楽部" && ./C1_cursor/browser_automation/untrack_secrets.sh

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
if git rm --cached C1_cursor/browser_automation/.env C1_cursor/browser_automation/config_nichinoken.yaml 2>/dev/null; then
  echo "追跡を外しました。変更をコミットするとリポジトリからこれらが削除され、.gitignore により今後はコミットされません。"
else
  echo "これらのファイルはすでに追跡されていません（または .git にアクセスできません）。"
fi
