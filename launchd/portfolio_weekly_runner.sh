#!/bin/zsh
# 資産全体の週次 Web 収集（日曜 09:10 ＋ Mac 起動時 RunAtLoad ＋ 朝オープン取りこぼし）
# 担当係: 618 資産記録・エビデンス係（docs/AIエージェントチーム/600_リソース・家計室/618_資産記録・エビデンス係）
# 成功済みの ISO 週は scripts 側でスキップ。手動は KURASHIFT ホームのボタン or --force。
# 複数 spawn の同時実行を防ぐ（あかつき OTP 競合・成功結果の上書き防止）。
# Python fcntlで画像取得・手動worker・週次の排他を共有。
set -euo pipefail
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PY="${HOME}/selenium_env/venv/bin/python"
LOG_DIR="${HOME}/Library/Logs/jarvis_portfolio"
mkdir -p "$LOG_DIR"
STAMP="$(date +%Y%m%d_%H%M%S)"
LOG="${LOG_DIR}/weekly_${STAMP}.log"
# Python側で共通kernel lock。旧mkdir lockは稼働確認まで自動削除しない。
cd "$REPO_DIR"
export PYTHONUNBUFFERED=1

{
  echo "# start $(date '+%Y-%m-%d %H:%M:%S %z')"
  "$PY" -u "${REPO_DIR}/scripts/jarvis_portfolio_weekly.py" "$@"
  echo "# end exit=$?"
} >>"$LOG" 2>&1
