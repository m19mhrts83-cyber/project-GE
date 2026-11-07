#!/usr/bin/env bash
# ループウェア (jarvis-loopware) 本番デプロイ — リポジトリルートからのみ実行。
# Vercel Root Directory = apps/loopware。apps/loopware 配下から vercel deploy しない。
# ルート .vercel は通常 trade-desk 用のため、デプロイ中だけ一時切替して戻す。
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

if [[ -f .env.jarvis_private ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env.jarvis_private
  set +a
fi

: "${VERCEL_TOKEN:?VERCEL_TOKEN 未設定 (.env.jarvis_private)}"

ORG_ID="${VERCEL_ORG_ID:-team_NJph8Tc5cSqw7rZSrPOQMp00}"
PROJECT_ID="${VERCEL_LOOPWARE_PROJECT_ID:-prj_D6sckfsTtBzuO1kNEERuXCQ1nL8w}"
SCOPE="${VERCEL_SCOPE:-m19mhrts83-1211s-projects}"
PROD_HOST="jarvis-loopware.vercel.app"

echo "📎 loopware deploy: repo root → jarvis-loopware (rootDirectory=apps/loopware)"

BACKUP=""
if [[ -d .vercel ]]; then
  BACKUP=".vercel.bak-loopware-deploy-$$"
  cp -a .vercel "$BACKUP"
fi

cleanup() {
  if [[ -n "$BACKUP" && -d "$BACKUP" ]]; then
    rm -rf .vercel
    mv "$BACKUP" .vercel
    echo "📎 restored root .vercel"
  fi
}
trap cleanup EXIT

mkdir -p .vercel apps/loopware/.vercel
cat > .vercel/project.json <<EOF
{
  "projectId": "$PROJECT_ID",
  "orgId": "$ORG_ID",
  "projectName": "jarvis-loopware",
  "settings": {
    "framework": "nextjs",
    "rootDirectory": "apps/loopware"
  }
}
EOF
cp .vercel/project.json apps/loopware/.vercel/project.json

export VERCEL_ORG_ID="$ORG_ID"
export VERCEL_PROJECT_ID="$PROJECT_ID"

npx --yes vercel pull --yes --environment=production --token "$VERCEL_TOKEN"
npx --yes vercel build --prod --token "$VERCEL_TOKEN"
DEPLOY_OUT="$(npx --yes vercel deploy --prebuilt --prod --yes --token "$VERCEL_TOKEN" 2>&1 | tee /dev/stderr)"
DEPLOY_URL="$(printf '%s\n' "$DEPLOY_OUT" | rg -o 'https://jarvis-loopware[^ ]+\.vercel\.app' | head -1 || true)"
if [[ -z "$DEPLOY_URL" ]]; then
  DEPLOY_URL="$(printf '%s\n' "$DEPLOY_OUT" | rg -o 'https://[^ ]+\.vercel\.app' | head -1 || true)"
fi
if [[ -n "$DEPLOY_URL" ]]; then
  npx --yes vercel alias set "$DEPLOY_URL" "$PROD_HOST" --token "$VERCEL_TOKEN" --scope "$SCOPE"
fi

echo "📎 本番: https://$PROD_HOST"
[[ -n "${DEPLOY_URL:-}" ]] && echo "📎 デプロイURL: $DEPLOY_URL"
