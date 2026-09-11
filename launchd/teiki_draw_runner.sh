#!/bin/zsh
# テイチャン（定期払いチャンス）自動確認・抽選
# 券があれば自動で抽選。ユーザー操作不要。
# 月・木 10:15 JST（Mac 起動中）＋朝オープン取りこぼし
set -euo pipefail
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PY="${HOME}/selenium_env/venv/bin/python"
LOG_DIR="${HOME}/Library/Logs/jarvis_teiki"
mkdir -p "$LOG_DIR"
STAMP="$(date +%Y%m%d_%H%M%S)"
LOG="${LOG_DIR}/run_${STAMP}.log"

cd "$REPO_DIR"
export PYTHONUNBUFFERED=1
if [[ -f "${REPO_DIR}/.env.jarvis_private" ]]; then
  set +e
  set -a
  # shellcheck disable=SC1091
  source "${REPO_DIR}/.env.jarvis_private" 2>>"${LOG_DIR}/env_source.err.log"
  set +a
  set -e
fi

{
  echo "# start $(date '+%Y-%m-%d %H:%M:%S %z')"
  # Mac 本線: Chrome CDP（セッション維持）。券があれば抽選まで自動。
  # GHA だけ --headless（Vpass は失敗しやすい）
  "$PY" -u "${REPO_DIR}/scripts/jarvis_teiki_barai_chance.py" --run --push
  echo "# end exit=$?"
} >>"$LOG" 2>&1
