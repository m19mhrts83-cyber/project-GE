#!/usr/bin/env python3
"""
Jarvis: OneDrive（Microsoft Graph）読取。

認証優先順:
  1) MS_GRAPH_REFRESH_TOKEN（個人用 OneDrive 向け・委任。推奨）
  2) MS_GRAPH_CLIENT_SECRET + TENANT/CLIENT + UPN|DRIVE_ID（職場テナントのアプリ専用）
  3) ローカル CloudStorage（Mac のみ）

初回（個人用）:
  python scripts/jarvis_ms_graph_device_login.py
  → .env.jarvis_private に MS_GRAPH_* を追記

確認:
  python scripts/jarvis_onedrive_graph.py --dry-run
  python scripts/jarvis_onedrive_graph.py --path "215_神・大家さん倶楽部/…"
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
LOCAL_ONEDRIVE = Path.home() / "Library/CloudStorage/OneDrive-個人用"
TOKEN_CACHE = Path.home() / ".jarvis_state" / "ms_graph_token_cache.json"


def _env(name: str) -> str:
    return (os.environ.get(name) or "").strip()


def has_refresh_auth() -> bool:
    return bool(_env("MS_GRAPH_CLIENT_ID") and _env("MS_GRAPH_REFRESH_TOKEN"))


def has_app_auth() -> bool:
    return bool(
        _env("MS_GRAPH_TENANT_ID")
        and _env("MS_GRAPH_CLIENT_ID")
        and _env("MS_GRAPH_CLIENT_SECRET")
        and (_env("MS_GRAPH_USER_UPN") or _env("MS_GRAPH_DRIVE_ID"))
    )


def graph_configured() -> bool:
    return has_refresh_auth() or has_app_auth()


def _post_form(url: str, data: dict[str, str]) -> dict[str, Any]:
    body = urllib.parse.urlencode(data).encode()
    req = urllib.request.Request(
        url, data=body, headers={"Content-Type": "application/x-www-form-urlencoded"}
    )
    try:
        with urllib.request.urlopen(req, timeout=45) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")[:400]
        raise RuntimeError(f"token HTTP {e.code}: {detail}") from e


def _tenant_authority() -> str:
    # consumers = 個人 MSA、organizations = 職場、common = 両方
    return _env("MS_GRAPH_AUTHORITY") or "consumers"


def refresh_access_token() -> str:
    """委任フローの refresh → access。キャッシュあり。"""
    if TOKEN_CACHE.is_file():
        try:
            cached = json.loads(TOKEN_CACHE.read_text(encoding="utf-8"))
            if float(cached.get("expires_at") or 0) > time.time() + 60:
                tok = cached.get("access_token") or ""
                if tok:
                    return tok
        except Exception:
            pass

    client_id = _env("MS_GRAPH_CLIENT_ID")
    refresh = _env("MS_GRAPH_REFRESH_TOKEN")
    secret = _env("MS_GRAPH_CLIENT_SECRET")  # 公開クライアントなら空で可
    auth = _tenant_authority()
    url = f"https://login.microsoftonline.com/{auth}/oauth2/v2.0/token"
    form: dict[str, str] = {
        "client_id": client_id,
        "grant_type": "refresh_token",
        "refresh_token": refresh,
        "scope": "offline_access Files.Read Files.Read.All User.Read",
    }
    if secret:
        form["client_secret"] = secret
    data = _post_form(url, form)
    access = data["access_token"]
    expires_in = int(data.get("expires_in") or 3600)
    new_refresh = data.get("refresh_token")
    TOKEN_CACHE.parent.mkdir(parents=True, exist_ok=True)
    TOKEN_CACHE.write_text(
        json.dumps(
            {
                "access_token": access,
                "expires_at": time.time() + expires_in,
                "obtained_at": time.time(),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    TOKEN_CACHE.chmod(0o600)
    if new_refresh and new_refresh != refresh:
        # 回転された refresh は stderr で案内のみ（自動で .env は書き換えない）
        print(
            "# note: refresh_token が回転しました。"
            " 新しい値を MS_GRAPH_REFRESH_TOKEN に反映してください"
            "（scripts/jarvis_ms_graph_device_login.py --print-refresh）。",
            file=sys.stderr,
        )
        rot = Path.home() / ".jarvis_state" / "ms_graph_new_refresh.env"
        rot.write_text(f"MS_GRAPH_REFRESH_TOKEN={new_refresh}\n", encoding="utf-8")
        rot.chmod(0o600)
        print(f"# wrote {rot}（反映後に削除）", file=sys.stderr)
    return access


def get_app_token() -> str:
    tenant = _env("MS_GRAPH_TENANT_ID")
    client_id = _env("MS_GRAPH_CLIENT_ID")
    client_secret = _env("MS_GRAPH_CLIENT_SECRET")
    url = f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token"
    return _post_form(
        url,
        {
            "client_id": client_id,
            "client_secret": client_secret,
            "scope": "https://graph.microsoft.com/.default",
            "grant_type": "client_credentials",
        },
    )["access_token"]


def get_access_token() -> str:
    if has_refresh_auth():
        return refresh_access_token()
    if has_app_auth():
        return get_app_token()
    raise RuntimeError("MS_GRAPH_* 未設定（refresh または app 認証）")


def read_file_local(rel_path: str) -> bytes:
    p = LOCAL_ONEDRIVE / rel_path
    if not p.is_file():
        raise FileNotFoundError(p)
    return p.read_bytes()


def read_file_graph(rel_path: str) -> bytes:
    token = get_access_token()
    drive_id = _env("MS_GRAPH_DRIVE_ID")
    upn = _env("MS_GRAPH_USER_UPN")
    encoded = "/".join(urllib.parse.quote(seg) for seg in rel_path.strip("/").split("/"))
    if drive_id:
        api = f"https://graph.microsoft.com/v1.0/drives/{drive_id}/root:/{encoded}:/content"
    elif has_refresh_auth() and not upn:
        # 委任: サインインユーザー自身の drive
        api = f"https://graph.microsoft.com/v1.0/me/drive/root:/{encoded}:/content"
    elif upn:
        api = (
            f"https://graph.microsoft.com/v1.0/users/{urllib.parse.quote(upn)}"
            f"/drive/root:/{encoded}:/content"
        )
    else:
        api = f"https://graph.microsoft.com/v1.0/me/drive/root:/{encoded}:/content"
    req = urllib.request.Request(api, headers={"Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.read()
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")[:500]
        raise RuntimeError(f"graph read HTTP {e.code}: {detail}") from e


def read_file(provider: str, path: str) -> bytes:
    """共通インターフェース。provider: onedrive | local"""
    provider = (provider or "onedrive").lower()
    if provider in ("onedrive", "graph"):
        if graph_configured():
            return read_file_graph(path)
        return read_file_local(path)
    if provider == "local":
        return read_file_local(path)
    raise ValueError(f"unknown provider: {provider}")


def probe_me(token: str) -> dict[str, Any]:
    req = urllib.request.Request(
        "https://graph.microsoft.com/v1.0/me?$select=displayName,userPrincipalName,mail,id",
        headers={"Authorization": f"Bearer {token}"},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--path", default="")
    ap.add_argument("--provider", default="onedrive")
    ap.add_argument("--probe", action="store_true", help="token 取得＋ /me 確認")
    args = ap.parse_args(argv)

    status: dict[str, Any] = {
        "graph_configured": graph_configured(),
        "auth_mode": (
            "refresh" if has_refresh_auth() else ("app" if has_app_auth() else "none")
        ),
        "local_onedrive_exists": LOCAL_ONEDRIVE.is_dir(),
        "provider": args.provider,
        "authority": _tenant_authority() if has_refresh_auth() else (_env("MS_GRAPH_TENANT_ID") or None),
    }
    if args.dry_run and not args.probe and not args.path:
        print(json.dumps(status, ensure_ascii=False, indent=2))
        if not graph_configured():
            print(
                "# 未設定。個人用 OneDrive は:\n"
                "#   1) Azure でアプリ登録（個人アカウント対応）\n"
                "#   2) python scripts/jarvis_ms_graph_device_login.py\n"
                "# 手順: docs/Jarvis_OneDrive_Graph.md",
                file=sys.stderr,
            )
        return 0

    if args.probe or (graph_configured() and not args.path):
        try:
            tok = get_access_token()
            me = probe_me(tok)
            status["probe_ok"] = True
            status["me"] = {
                "displayName": me.get("displayName"),
                "userPrincipalName": me.get("userPrincipalName"),
                "mail": me.get("mail"),
            }
        except Exception as e:
            status["probe_ok"] = False
            status["probe_error"] = str(e)[:300]
            print(json.dumps(status, ensure_ascii=False, indent=2))
            return 1
        print(json.dumps(status, ensure_ascii=False, indent=2))
        if not args.path:
            return 0

    data = read_file(args.provider, args.path)
    print(
        json.dumps(
            {
                **status,
                "path": args.path,
                "bytes": len(data),
                "preview": data[:120].decode("utf-8", errors="replace"),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
