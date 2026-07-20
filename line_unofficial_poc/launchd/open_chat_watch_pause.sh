#!/bin/zsh
# パートナー確認バッチ等の前に常駐監視を一時停止する。
set -euo pipefail
UID_VALUE="$(id -u)"
LABEL="com.matsunoma.line.openchat.watch"
launchctl bootout "gui/${UID_VALUE}/${LABEL}" > /dev/null 2>&1 || true
launchctl disable "gui/${UID_VALUE}/${LABEL}" > /dev/null 2>&1 || true
echo "[watch] paused: ${LABEL}"
