#!/usr/bin/env python3
"""
Jarvis: Microsoft Graph（OneDrive）設定チェック＋手順の短案内

  python scripts/jarvis_ms_graph_setup_check.py
  python scripts/jarvis_ms_graph_setup_check.py --json

未設定でも exit 0（案内）。--require で未設定時 exit 2。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
from jarvis_onedrive_graph import (  # noqa: E402
    LOCAL_ONEDRIVE,
    graph_configured,
    has_app_auth,
    has_refresh_auth,
)


def guide_personal() -> str:
    return """
【推奨・個人用 OneDrive（OneDrive-個人用）】
アプリ専用（client credentials）は個人 MSA では実質使えないことが多いです。
委任＋デバイスコード（約10分・初回のみ）:

  1. https://portal.azure.com → Microsoft Entra ID → アプリの登録 → 新規
  2. 名前: jarvis-onedrive-readonly
     サポートされるアカウントの種類:
       「個人の Microsoft アカウントのみ」または「任意の組織＋個人」
  3. 認証 → 高度な設定 → 「パブリック クライアント フローを許可」= はい
     （デバイスコード用。リダイレクト URI は空でも可）
  4. API のアクセス許可 → Microsoft Graph → 【委任されたアクセス許可】
       Files.Read / Files.Read.All / offline_access / User.Read
     ※「アプリケーションの許可」の Files.Read.All は今回不要
  5. 概要の アプリケーション(クライアント)ID を控える
  6. .env.jarvis_private に（値はチャットに貼らない）:
       MS_GRAPH_CLIENT_ID=...
       MS_GRAPH_AUTHORITY=consumers
  7. python scripts/jarvis_ms_graph_device_login.py
       → 表示 URL を開き、OneDrive と同じ Microsoft アカウントで承認
  8. ~/.jarvis_state/ms_graph_device_login.env を .env.jarvis_private へ追記
  9. python scripts/jarvis_onedrive_graph.py --probe
 10. python scripts/jarvis_ms_graph_secrets_to_gha.py
 11. gh workflow run jarvis-dashboard-lanes.yml

詳細: docs/Jarvis_OneDrive_Graph.md
""".strip()


def guide_work() -> str:
    return """
【職場テナントのみ・アプリ専用】
  MS_GRAPH_TENANT_ID / CLIENT_ID / CLIENT_SECRET / USER_UPN（または DRIVE_ID）
  アプリケーションの許可 Files.Read.All ＋ 管理者の同意
""".strip()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--require", action="store_true")
    args = ap.parse_args(argv)

    status = {
        "graph_configured": graph_configured(),
        "auth_mode": (
            "refresh" if has_refresh_auth() else ("app" if has_app_auth() else "none")
        ),
        "local_onedrive_exists": LOCAL_ONEDRIVE.is_dir(),
        "gha_lanes": "MS_GRAPH_REFRESH_TOKEN またはアプリ専用 Secrets があれば収集を試行",
        "note": "個人用 OneDrive は refresh（委任）経路を推奨",
    }
    if args.json:
        print(json.dumps(status, ensure_ascii=False, indent=2))
    else:
        print(f"graph_configured: {status['graph_configured']}")
        print(f"auth_mode: {status['auth_mode']}")
        print(f"local_onedrive: {status['local_onedrive_exists']}")
        if not status["graph_configured"]:
            print()
            print(guide_personal())
            print()
            print(guide_work())
        else:
            print("OK — 環境変数は揃っています。")
            print("  python scripts/jarvis_onedrive_graph.py --probe")
            print("  python scripts/jarvis_ms_graph_secrets_to_gha.py  # GHA 未反映なら")
    if args.require and not status["graph_configured"]:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
