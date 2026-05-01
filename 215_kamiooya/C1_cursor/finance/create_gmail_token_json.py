#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Gmail API 用の token JSON（authorized_user_info）を作成する。

用途:
- プルデンシャル確認番号（OTP）を Gmail API で取得するために、対象 Gmail アカウントで OAuth 同意し
  `token_*.json` を作る（例: token_m19m.json, token_chk59.json）。

注意:
- 既定のスコープは 215 共通（readonly/modify/send）。他のスクリプトと共用してスコープ欠落を防ぐ。
- 初回はブラウザが開く。完了後、token JSON を指定パスへ保存する。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _load_215_scopes() -> list[str]:
    # finance 側でも 1b のスコープ定義を正とする
    manual_dir = Path(__file__).resolve().parent.parent / "1b_Cursorマニュアル"
    sys.path.insert(0, str(manual_dir))
    from gmail_api_scopes import GMAIL_SCOPES_215  # noqa: E402

    return list(GMAIL_SCOPES_215)


def main() -> int:
    ap = argparse.ArgumentParser(description="Gmail API token JSON を作成")
    ap.add_argument(
        "--credentials",
        default="",
        help="OAuth クライアント（credentials.json）。未指定時は 1b_Cursorマニュアル/credentials.json",
    )
    ap.add_argument(
        "--out",
        required=True,
        help="保存先 token JSON パス（例: /.../1b_Cursorマニュアル/token_chk59.json）",
    )
    ap.add_argument(
        "--no-local-server",
        action="store_true",
        help="ローカルサーバ方式を使わずコンソール方式にする（環境により必要）",
    )
    args = ap.parse_args()

    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build

    manual_dir = Path(__file__).resolve().parent.parent / "1b_Cursorマニュアル"
    cred_path = (
        Path(args.credentials).expanduser()
        if (args.credentials or "").strip()
        else (manual_dir / "credentials.json")
    )
    if not cred_path.is_file():
        raise SystemExit(f"credentials.json が見つかりません: {cred_path}")

    out_path = Path(args.out).expanduser()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    scopes = _load_215_scopes()
    flow = InstalledAppFlow.from_client_secrets_file(str(cred_path), scopes=scopes)
    if args.no_local_server:
        creds = flow.run_console()
    else:
        creds = flow.run_local_server(port=0)

    out_path.write_text(creds.to_json(), encoding="utf-8")

    # どのアカウントで認可したかを表示（チャットには token の中身を出さない）
    try:
        svc = build("gmail", "v1", credentials=creds)
        prof = svc.users().getProfile(userId="me").execute()
        em = (prof.get("emailAddress") or "").strip()
    except Exception:
        em = ""

    print(f"✅ token 保存: {out_path}")
    if em:
        print(f"✅ Gmail API アカウント: {em}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

