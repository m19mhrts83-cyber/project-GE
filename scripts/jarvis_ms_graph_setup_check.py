#!/usr/bin/env python3
"""
Jarvis: Microsoft Graph（OneDrive）設定チェック＋ Azure 手順の短案内

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
from jarvis_onedrive_graph import LOCAL_ONEDRIVE, graph_configured  # noqa: E402

NEEDED = (
    "MS_GRAPH_TENANT_ID",
    "MS_GRAPH_CLIENT_ID",
    "MS_GRAPH_CLIENT_SECRET",
)


def missing_vars() -> list[str]:
    miss = [k for k in NEEDED if not (os.environ.get(k) or "").strip()]
    if not (os.environ.get("MS_GRAPH_USER_UPN") or "").strip() and not (
        os.environ.get("MS_GRAPH_DRIVE_ID") or ""
    ).strip():
        miss.append("MS_GRAPH_USER_UPN|MS_GRAPH_DRIVE_ID")
    return miss


def guide() -> str:
    return """
Azure 側（約10分・初回のみ）:
  1. https://portal.azure.com → Microsoft Entra ID → アプリの登録 → 新規
  2. 名前例: jarvis-onedrive-readonly / シングルテナント
  3. API のアクセス許可 → Microsoft Graph → アプリケーションの許可
     → Files.Read.All （必要なら Sites.Read.All）→ 管理者の同意
  4. 証明書とシークレット → 新しいクライアント シークレット → 値をコピー
  5. 概要の ディレクトリ(テナント)ID / アプリケーション(クライアント)ID を控える
  6. .env.jarvis_private に:
       MS_GRAPH_TENANT_ID=...
       MS_GRAPH_CLIENT_ID=...
       MS_GRAPH_CLIENT_SECRET=...
       MS_GRAPH_USER_UPN=（OneDrive 個人用のサインイン UPN）
     または MS_GRAPH_DRIVE_ID=...
  7. GitHub Secrets に同名を追加（lanes GHA 用）
  8. python scripts/jarvis_onedrive_graph.py --dry-run
     → graph_configured: true
  詳細テンプレ: config/onedrive_graph.example.yaml
""".strip()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--require", action="store_true")
    args = ap.parse_args(argv)

    miss = missing_vars()
    status = {
        "graph_configured": graph_configured(),
        "local_onedrive_exists": LOCAL_ONEDRIVE.is_dir(),
        "missing": miss,
        "gha_lanes": "MS_GRAPH_* が Secrets にあれば jarvis-dashboard-lanes.yml が収集を試行",
    }
    if args.json:
        print(json.dumps(status, ensure_ascii=False, indent=2))
    else:
        print(f"graph_configured: {status['graph_configured']}")
        print(f"local_onedrive: {status['local_onedrive_exists']}")
        if miss:
            print("missing:", ", ".join(miss))
            print()
            print(guide())
        else:
            print("OK — Graph 用環境変数は揃っています。--dry-run で通信確認を。")
            print("  python scripts/jarvis_onedrive_graph.py --dry-run")
    if args.require and not status["graph_configured"]:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
