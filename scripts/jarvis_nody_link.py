"""Slack などに貼る Nody（apps/loopware）のリンクを作る共通部品。

Nody は本番で入場の鍵（LOOPWARE_ACCESS_KEY）があるため、素のリンクだと
Cookie の無い端末（Slack から開いたブラウザなど）では /login で止められる。

- 投稿する側が鍵を持っていれば ?t=<期限>.<署名>（7日）付きの直リンク
  （作り方は apps/loopware/lib/access.ts の linkToken と同じ）
- 鍵が無ければ Jarvis ダッシュボード経由 /go/loopware?to=<パス>
  （ダッシュがログインを確認し、通行証つきで Nody へ飛ばす。ダッシュ側は鍵を持っている）
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import urllib.parse
from datetime import datetime, timezone

LOOPWARE_DEFAULT = "https://jarvis-loopware.vercel.app"
DASHBOARD_DEFAULT = "https://jarvis-dashboard-amber.vercel.app"


def loopware_base() -> str:
    return (
        (os.environ.get("JARVIS_LOOPWARE_URL") or "").strip().rstrip("/")
        or (os.environ.get("LOOPWARE_URL") or "").strip().rstrip("/")
        or (os.environ.get("NEXT_PUBLIC_LOOPWARE_URL") or "").strip().rstrip("/")
        or LOOPWARE_DEFAULT
    )


def dashboard_base() -> str:
    return (os.environ.get("JARVIS_DASHBOARD_URL") or "").strip().rstrip("/") or DASHBOARD_DEFAULT


def link_token(key: str, now: datetime, days: int = 7) -> str:
    """apps/loopware/lib/access.ts の linkToken と同じ作り方。"""
    exp = int(now.timestamp()) + days * 86400
    sig = hmac.new(key.encode(), f"loopware-link-v1:{exp}".encode(), hashlib.sha256).digest()
    return f"{exp}." + base64.urlsafe_b64encode(sig).decode().rstrip("=")


def nody_link(path: str, now: datetime | None = None) -> str:
    """Nody 内のパス（例 '/312?topic=..'）を、Slack から開いても入れるリンクにする。"""
    if not path.startswith("/"):
        path = "/" + path
    key = (os.environ.get("LOOPWARE_ACCESS_KEY") or "").strip()
    if key:
        url = f"{loopware_base()}{path}"
        return url + ("&" if "?" in url else "?") + "t=" + link_token(key, now or datetime.now(timezone.utc))
    return f"{dashboard_base()}/go/loopware?to=" + urllib.parse.quote(path, safe="/")
