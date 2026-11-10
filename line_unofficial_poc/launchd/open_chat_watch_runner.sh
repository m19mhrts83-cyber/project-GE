#!/bin/zsh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$REPO_DIR"

if [[ -f ".env" ]]; then
  set -a
  source ".env"
  set +a
fi

ROUTES_YAML="${LINE_OPEN_CHAT_ROUTES_YAML:-$REPO_DIR/open_chat_routes.yaml}"

if [[ ! -f "$ROUTES_YAML" ]]; then
  echo "[watch] routes yaml が見つかりません: $ROUTES_YAML" >&2
  exit 1
fi

if [[ ! -x "$REPO_DIR/run_patch.sh" ]]; then
  echo "[watch] run_patch.sh が見つかりません: $REPO_DIR/run_patch.sh" >&2
  exit 1
fi

# 公式Mac版LINEとCHRLINEは同じデスクトップ認証枠を競合する。
# Mac版が起動中はトークンを消費せず待機し、終了後に自動再開する。
notified=0
while /usr/bin/pgrep -f 'application\.jp\.naver\.line\.mac|/Applications/LINE\.app' > /dev/null 2>&1; do
  if [[ "$notified" -eq 0 ]]; then
    echo "[watch] Mac版LINEが起動中のため待機します（終了後に自動再開）。" >&2
    /usr/bin/osascript -e 'display notification "Mac版LINEを終了すると監視を自動再開します" with title "LINE Open Chat" subtitle "デスクトップ認証の競合を防止中"' > /dev/null 2>&1 || true
    notified=1
  fi
  sleep 30
done

# 常駐は QR 禁止。保存トークンが無効になると chrline_client_utils が「再ログインが必要」印を書く。
# 印がある間は LINE に触らず待つ（KeepAlive による起動のくり返し・403 の連打を防ぐ。2026-11-10）。
# QR 再ログインに成功すると印が消え、ここを抜けて監視が再開する。
GUARD="$REPO_DIR/watch_relogin_guard.py"
waiting=0
while ! /usr/bin/python3 "$GUARD" --check; do
  if [[ "$waiting" -eq 0 ]]; then
    echo "[watch] 再ログイン待ち（印: watch_relogin_required.json）。LINE には触らず待機します" >&2
    /usr/bin/python3 "$GUARD" --notify || true
    waiting=1
  fi
  sleep "${LINE_WATCH_RELOGIN_POLL_SEC:-300}"
done

set +e
"$REPO_DIR/run_patch.sh" chrline_open_chat_realtime_watch.py --routes-yaml "$ROUTES_YAML" --verbose
rc=$?
set -e
if /usr/bin/python3 "$GUARD" --check; then
  exit "$rc"
fi
# 今回の終了で印が付いた → #ops に 1 回だけ知らせ、次の起動からは上の待機に入る
/usr/bin/python3 "$GUARD" --notify || true
exit 0
