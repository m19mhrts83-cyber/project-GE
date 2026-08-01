#!/usr/bin/env python3
"""
Jarvis: 個人用 OneDrive 向け Microsoft Graph デバイスコードログイン（初回1回）

前提（ユーザーが Azure で実施）:
  - アプリ登録名例: jarvis-onedrive-readonly
  - サポートされるアカウント: 「個人の Microsoft アカウント」または「両方」
  - プラットフォーム: モバイルとデスクトップ / パブリック クライアント（デバイスコード可）
  - 委任のアクセス許可: Files.Read, Files.Read.All, offline_access, User.Read
  - （個人アカウントでは「アプリケーションの許可 Files.Read.All」は使わない）

使い方:
  cd ~/git-repos && set -a && source .env.jarvis_private && set +a
  # CLIENT_ID だけ先に入れておくか、--client-id で渡す
  python scripts/jarvis_ms_graph_device_login.py
  # 表示された URL を開きコードを入力（OneDrive と同じ Microsoft アカウント）
  # 成功後: ~/.jarvis_state/ms_graph_device_login.env に追記用が出る
  # → .env.jarvis_private へコピーして「保存した」

オプション:
  --client-id GUID
  --authority consumers|common   （既定 consumers）
  --print-refresh                キャッシュ回転分の refresh を表示せずパスだけ
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

OUT = Path.home() / ".jarvis_state" / "ms_graph_device_login.env"
SCOPES = "offline_access Files.Read Files.Read.All User.Read"


def _post(url: str, data: dict[str, str]) -> dict:
    body = urllib.parse.urlencode(data).encode()
    req = urllib.request.Request(
        url, data=body, headers={"Content-Type": "application/x-www-form-urlencoded"}
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        try:
            payload = json.loads(raw)
        except Exception:
            raise SystemExit(f"HTTP {e.code}: {raw[:500]}") from e
        err = str(payload.get("error") or "")
        if err in ("authorization_pending", "slow_down"):
            return {"error": err, **payload}
        raise SystemExit(f"HTTP {e.code}: {raw[:500]}") from e


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--client-id", default=os.environ.get("MS_GRAPH_CLIENT_ID", "").strip())
    ap.add_argument(
        "--client-secret",
        default=os.environ.get("MS_GRAPH_CLIENT_SECRET", "").strip(),
        help="機密クライアントのときだけ。公開クライアントなら空",
    )
    ap.add_argument(
        "--authority",
        default=(os.environ.get("MS_GRAPH_AUTHORITY") or "consumers").strip(),
        help="consumers（個人） / common（両方）",
    )
    args = ap.parse_args(argv)
    if not args.client_id:
        raise SystemExit(
            "MS_GRAPH_CLIENT_ID がありません。"
            " Azure でアプリ登録後、.env.jarvis_private に CLIENT_ID を書いてから再実行するか"
            " --client-id を渡してください。"
        )

    base = f"https://login.microsoftonline.com/{args.authority}/oauth2/v2.0"
    device = _post(
        f"{base}/devicecode",
        {
            "client_id": args.client_id,
            "scope": SCOPES,
        },
    )
    if device.get("error"):
        raise SystemExit(f"devicecode failed: {device}")
    print()
    print("===== Microsoft ログイン（個人用 OneDrive）=====")
    print(device.get("message") or "")
    print(f"URL : {device.get('verification_uri')}")
    print(f"CODE: {device.get('user_code')}")
    print("OneDrive-個人用 と同じ Microsoft アカウントで承認してください。")
    print("================================================")
    print()

    interval = int(device.get("interval") or 5)
    expires = int(device.get("expires_in") or 900)
    deadline = time.time() + expires
    form = {
        "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
        "client_id": args.client_id,
        "device_code": device["device_code"],
    }
    if args.client_secret:
        form["client_secret"] = args.client_secret

    token: dict | None = None
    while time.time() < deadline:
        time.sleep(interval)
        resp = _post(f"{base}/token", form)
        err = resp.get("error")
        if err == "authorization_pending":
            print("…待機中", flush=True)
            continue
        if err == "slow_down":
            interval += 5
            continue
        if err:
            raise SystemExit(f"token error: {resp}")
        token = resp
        break

    if not token:
        raise SystemExit("タイムアウト: デバイスコードの承認が完了しませんでした")

    refresh = token.get("refresh_token") or ""
    if not refresh:
        raise SystemExit("refresh_token が返りませんでした（offline_access を確認）")

    lines = [
        f"MS_GRAPH_CLIENT_ID={args.client_id}",
        f"MS_GRAPH_AUTHORITY={args.authority}",
        f"MS_GRAPH_REFRESH_TOKEN={refresh}",
    ]
    if args.client_secret:
        lines.append(f"MS_GRAPH_CLIENT_SECRET={args.client_secret}")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    OUT.chmod(0o600)

    access = token["access_token"]
    req = urllib.request.Request(
        "https://graph.microsoft.com/v1.0/me?$select=displayName,userPrincipalName,mail",
        headers={"Authorization": f"Bearer {access}"},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        me = json.load(r)
    print("login_ok")
    print("me:", me.get("displayName"), me.get("userPrincipalName") or me.get("mail"))
    print(f"wrote {OUT}")
    print("次: このファイルの内容を .env.jarvis_private に追記 → 『保存した』")
    print("その後: python scripts/jarvis_ms_graph_secrets_to_gha.py")
    print("確認: python scripts/jarvis_onedrive_graph.py --probe")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
