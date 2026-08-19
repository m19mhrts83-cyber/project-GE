#!/usr/bin/env bash
# KURASHIFT (jarvis-trade-desk) 本番デプロイ — リポジトリルートからのみ実行。
# Vercel の Root Directory は apps/trade-desk。apps/trade-desk 配下から vercel deploy しない。
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

export VERCEL_ORG_ID="${VERCEL_ORG_ID:-team_NJph8Tc5cSqw7rZSrPOQMp00}"
export VERCEL_PROJECT_ID="${VERCEL_TRADE_DESK_PROJECT_ID:-prj_FoZQmiplAx31rMNxS7sodjYubyto}"

echo "📎 KURASHIFT deploy: repo root → jarvis-trade-desk (rootDirectory=apps/trade-desk)"

if [[ ! -f .vercel/project.json ]]; then
  echo "WARN: .vercel/project.json がありません。vercel link でルートをリンクしてください。" >&2
fi

npx --yes vercel pull --yes --environment=production --token "$VERCEL_TOKEN"
npx --yes vercel build --prod --token "$VERCEL_TOKEN"
npx --yes vercel deploy --prebuilt --prod --yes --token "$VERCEL_TOKEN"

echo "📎 本番: https://jarvis-trade-desk.vercel.app"
