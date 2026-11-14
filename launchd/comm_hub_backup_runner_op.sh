#!/bin/zsh
# comm_hub_backup_runner.sh の 1Password 版（試行 2026-11-15）。元の runner と plist はそのまま残す。
# 秘密のうち config/op/comm_hub_backup.env に書いたキーだけ 1Password（Service Account）から読む。
# それ以外（MS Graph など）はこれまでどおり .env.jarvis_private。
# Service Account のトークンはキーチェーン（サービス名 op-sa-jarvis-agents）。値はログに出さない。
set -uo pipefail
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PY="${HOME}/selenium_env/venv/bin/python"
OP="/usr/local/bin/op"
OP_ENV_FILE="${REPO_DIR}/config/op/comm_hub_backup.env"
LOG_DIR="${HOME}/Library/Logs/jarvis_comm_hub_backup"
mkdir -p "$LOG_DIR"
cd "$REPO_DIR"
find "$LOG_DIR" -name 'backup_*.log' -mtime +30 -delete 2>/dev/null || true

PRIVATE_ENV="${HOME}/git-repos/.env.jarvis_private"
[[ -f "$PRIVATE_ENV" ]] || PRIVATE_ENV="${REPO_DIR}/.env.jarvis_private"
if [[ ! -f "$PRIVATE_ENV" ]]; then
  echo "private environment file is missing" >&2
  exit 2
fi
set -a
# shellcheck disable=SC1091
source "$PRIVATE_ENV"
set +a

# 1Password に移したキーは .env 側を消しておく（1Password から読めなければはっきり失敗させる）
for k in $(grep -E '^[A-Z_][A-Z0-9_]*=' "$OP_ENV_FILE" | cut -d= -f1); do
  unset "$k"
done

OP_SERVICE_ACCOUNT_TOKEN="$(/usr/bin/security find-generic-password -a "$USER" -s "op-sa-jarvis-agents" -w 2>/dev/null)"
if [[ -z "$OP_SERVICE_ACCOUNT_TOKEN" ]]; then
  echo "op service account token is missing in keychain" >&2
  exit 3
fi
export OP_SERVICE_ACCOUNT_TOKEN

LOG="${LOG_DIR}/backup_$(date +%Y%m%d_%H%M%S).log"
{
  echo "# start $(date '+%Y-%m-%d %H:%M:%S %z') via=1password"
  "$OP" run --env-file="$OP_ENV_FILE" -- "$PY" "${REPO_DIR}/scripts/jarvis_comm_hub_backup.py" "$@"
  RC=$?
  echo "# end exit=${RC}"
} >>"$LOG" 2>&1
exit "${RC:-0}"
