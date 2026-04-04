#!/usr/bin/env python3
"""
CHRLINE-PatchV2 向け QR ログイン PoC。

install_chrline_patchv2_mac.sh 適用後、device=DESKTOPWIN, useThrift=True で
セッションを張る（PyPI 2.5.14 の CHROMEOS 既定より通りやすい可能性）。

token が短時間で失効するケースに備え、requestSQR3（secure）を使って
ログインし、取得 token を保存してから検証ログインまで行う。
"""
from __future__ import annotations

import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")


def main() -> int:
    from CHRLINE import CHRLINE

    from chrline_client_utils import (
        cleanup_chrline_qr_images,
        persist_auth_token,
        save_root_from_env,
    )

    p = save_root_from_env()
    cleanup_chrline_qr_images(p)

    # requestSQR2 経路では token が短命化するケースがあるため、secure フローを使う。
    cl = CHRLINE(device="DESKTOPWIN", useThrift=True, savePath=str(p), noLogin=True)
    try:
        for chunk in cl.requestSQR3(isSelf=True):
            text = str(chunk)
            # URL / QR画像パス / PIN表示だけ標準出力に出す（token 本文は出さない）。
            if text.startswith(("URL:", "IMG:", "請輸入pincode:")):
                print(text)
    finally:
        cleanup_chrline_qr_images(p)

    tok = getattr(cl, "authToken", None) or ""
    if tok.strip():
        persist_auth_token(p, tok)
        # 取得 token がそのまま利用可能かを直後に検証する。
        CHRLINE(tok, device="DESKTOPWIN", useThrift=True, savePath=str(p))
    print("ログイン完了（セッションは LINE_UNOFFICIAL_AUTH_DIR に保存された想定です）。")
    if not tok.strip():
        print(
            "注意: authToken が空です。QR を最後まで完了できていない可能性があります。",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
