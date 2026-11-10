#!/usr/bin/env bash
# GHA ジョブの最後に呼ぶ（if: always()）。復旧窓口・機械の予備の目印。
#   成功: sync_meta に job_ok:<job> = {"at":..., "source":"gha", "run":...} を書く（heartbeat）
#   窓口からの再実行（RECOVERY_ACTOR あり）: 結果を #ai-hub に1行（Webhook）
# 失敗しても本体の結果は変えない（常に exit 0）。秘密の値は出さない。
# 使い方: scripts/jarvis_job_finish.sh <job_id> <job.status>
set -uo pipefail
JOB="${1:?job id}"
STATUS="${2:-unknown}"
NOW="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
RUN_URL="${GITHUB_SERVER_URL:-https://github.com}/${GITHUB_REPOSITORY:-}/actions/runs/${GITHUB_RUN_ID:-}"
SOURCE="gha"
[[ -n "${RECOVERY_ACTOR:-}" ]] && SOURCE="gha:${RECOVERY_ACTOR}"

if [[ "$STATUS" == "success" && "${DRY:-false}" != "true" && -n "${JARVIS_SUPABASE_URL:-}" && -n "${JARVIS_SUPABASE_SERVICE_ROLE_KEY:-}" ]]; then
  VALUE=$(printf '{"at":"%s","source":"%s","run":"%s"}' "$NOW" "$SOURCE" "$RUN_URL" | sed 's/"/\\"/g')
  BODY=$(printf '{"key":"job_ok:%s","value":"%s","updated_at":"%s"}' "$JOB" "$VALUE" "$NOW")
  curl -sS -o /dev/null -w "heartbeat job_ok:${JOB} http=%{http_code}\n" -X POST \
    "${JARVIS_SUPABASE_URL}/rest/v1/sync_meta?on_conflict=key" \
    -H "apikey: ${JARVIS_SUPABASE_SERVICE_ROLE_KEY}" \
    -H "Authorization: Bearer ${JARVIS_SUPABASE_SERVICE_ROLE_KEY}" \
    -H "Content-Type: application/json" \
    -H "Prefer: resolution=merge-duplicates" \
    -d "$BODY" || echo "::warning::heartbeat write failed"
fi

if [[ -n "${RECOVERY_ACTOR:-}" && -n "${SLACK_WEBHOOK_AI_TEAM_HUB:-}" ]]; then
  case "$STATUS" in
    success) MARK="✅ 成功" ;;
    failure) MARK="❌ 失敗（Jarvis／松野さんへ）" ;;
    *) MARK="⚠️ ${STATUS}" ;;
  esac
  JST="$(TZ=Asia/Tokyo date +%m/%d\ %H:%M)"
  TEXT="🔧 再実行の結果｜${JOB}｜${RECOVERY_ACTOR}｜${JST} ${MARK}\n${RUN_URL}"
  curl -sS -o /dev/null -w "slack hub http=%{http_code}\n" -X POST "$SLACK_WEBHOOK_AI_TEAM_HUB" \
    -H "Content-Type: application/json" \
    -d "$(printf '{"text":"%s","username":"Jarvis 復旧窓口"}' "$TEXT")" || echo "::warning::slack post failed"
fi
exit 0
