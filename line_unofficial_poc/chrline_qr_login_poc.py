#!/usr/bin/env python3
"""
CHRLINE-PatchV2 向け QR ログイン PoC。

install_chrline_patchv2_mac.sh 適用後、フォーク付属の test/login_getToken_test.py と同様に
device=DESKTOPWIN, useThrift=True でセッションを張る（PyPI 2.5.14 の CHROMEOS 既定より通りやすい可能性）。

.env の LINE_UNOFFICIAL_AUTH_DIR にセッション保存。authToken は標準出力に出さない。
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")


def main() -> int:
    save = os.environ.get("LINE_UNOFFICIAL_AUTH_DIR", "").strip()
    if not save:
        print("エラー: .env に LINE_UNOFFICIAL_AUTH_DIR を設定してください。", file=sys.stderr)
        return 1
    p = Path(save)
    p.mkdir(parents=True, exist_ok=True)

    from CHRLINE import CHRLINE

    from chrline_client_utils import persist_auth_token

    cl = CHRLINE(device="DESKTOPWIN", useThrift=True, savePath=str(p))
    tok = getattr(cl, "authToken", None) or ""
    if tok.strip():
        persist_auth_token(p, tok)
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
