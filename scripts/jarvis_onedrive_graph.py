#!/usr/bin/env python3
"""
Jarvis: OneDrive（Microsoft Graph）読取ブリッジ骨格。

役割:
  - 原本は OneDrive（215 等）
  - ダッシュボード投影は Supabase
  - クラウド収集・クラウドエージェントは本モジュール経由でファイルを読む

  cd ~/git-repos && set -a && source .env.jarvis_private && set +a
  python scripts/jarvis_onedrive_graph.py --dry-run
  python scripts/jarvis_onedrive_graph.py --path "215_神・大家さん倶楽部/C2_ルーティン作業/26_パートナー社への相談/000_共通/連絡先一覧.yaml"

環境（`.env.jarvis_private`）:
  MS_GRAPH_TENANT_ID / MS_GRAPH_CLIENT_ID / MS_GRAPH_CLIENT_SECRET
  MS_GRAPH_USER_UPN … 読取対象（例: 個人用 OneDrive のアカウント UPN）
  または MS_GRAPH_DRIVE_ID

未設定時はローカル CloudStorage パスにフォールバック（Mac のみ）。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
LOCAL_ONEDRIVE = Path.home() / "Library/CloudStorage/OneDrive-個人用"


def graph_configured() -> bool:
    return bool(
        (os.environ.get("MS_GRAPH_TENANT_ID") or "").strip()
        and (os.environ.get("MS_GRAPH_CLIENT_ID") or "").strip()
        and (os.environ.get("MS_GRAPH_CLIENT_SECRET") or "").strip()
        and (
            (os.environ.get("MS_GRAPH_USER_UPN") or "").strip()
            or (os.environ.get("MS_GRAPH_DRIVE_ID") or "").strip()
        )
    )


def get_app_token() -> str:
    tenant = os.environ["MS_GRAPH_TENANT_ID"].strip()
    client_id = os.environ["MS_GRAPH_CLIENT_ID"].strip()
    client_secret = os.environ["MS_GRAPH_CLIENT_SECRET"].strip()
    url = f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token"
    body = urllib.parse.urlencode(
        {
            "client_id": client_id,
            "client_secret": client_secret,
            "scope": "https://graph.microsoft.com/.default",
            "grant_type": "client_credentials",
        }
    ).encode()
    req = urllib.request.Request(
        url, data=body, headers={"Content-Type": "application/x-www-form-urlencoded"}
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.load(r)
    return data["access_token"]


def read_file_local(rel_path: str) -> bytes:
    p = LOCAL_ONEDRIVE / rel_path
    if not p.is_file():
        raise FileNotFoundError(p)
    return p.read_bytes()


def read_file_graph(rel_path: str) -> bytes:
    token = get_app_token()
    drive_id = (os.environ.get("MS_GRAPH_DRIVE_ID") or "").strip()
    upn = (os.environ.get("MS_GRAPH_USER_UPN") or "").strip()
    # path は URL encode（スラッシュは path セグメントとして残す）
    encoded = "/".join(urllib.parse.quote(seg) for seg in rel_path.strip("/").split("/"))
    if drive_id:
        api = f"https://graph.microsoft.com/v1.0/drives/{drive_id}/root:/{encoded}:/content"
    else:
        api = (
            f"https://graph.microsoft.com/v1.0/users/{urllib.parse.quote(upn)}"
            f"/drive/root:/{encoded}:/content"
        )
    req = urllib.request.Request(api, headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read()


def read_file(provider: str, path: str) -> bytes:
    """共通インターフェース。provider: onedrive | local"""
    provider = (provider or "onedrive").lower()
    if provider in ("onedrive", "graph"):
        if graph_configured():
            return read_file_graph(path)
        # Mac フォールバック
        return read_file_local(path)
    if provider == "local":
        return read_file_local(path)
    raise ValueError(f"unknown provider: {provider}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--path", default="")
    ap.add_argument("--provider", default="onedrive")
    args = ap.parse_args(argv)

    status: dict[str, Any] = {
        "graph_configured": graph_configured(),
        "local_onedrive_exists": LOCAL_ONEDRIVE.is_dir(),
        "provider": args.provider,
    }
    if args.dry_run or not args.path:
        print(json.dumps(status, ensure_ascii=False, indent=2))
        if not graph_configured():
            print(
                "# MS_GRAPH_* 未設定。Azure AD アプリ＋Client Secret を "
                ".env.jarvis_private に追記後に Graph 読取が有効になります。",
                file=sys.stderr,
            )
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
