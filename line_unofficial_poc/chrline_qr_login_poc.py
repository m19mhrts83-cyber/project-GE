#!/usr/bin/env python3
"""
CHRLINE-PatchV2 向け QR ログイン PoC。

install_chrline_patchv2_mac.sh 適用後、device=DESKTOPWIN, useThrift=True で
セッションを張る（PyPI 2.5.14 の CHROMEOS 既定より通りやすい可能性）。

token が短時間で失効するケースに備え、requestSQR3（secure）を使って
ログインし、取得 token を保存してから検証ログインまで行う。
"""
from __future__ import annotations

import re
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")


def _extract_login_url_from_chunk_text(text: str) -> str | None:
    """
    requestSQR3 の chunk は環境/バージョンで文字列化のされ方が揺れる。
    - "URL: https://..." の形式
    - "{1: 'https://...'}" のような dict 表現
    """
    m = re.search(r"(https://line\.me/R/au/lgn/sq/[A-Za-z0-9]+)", text)
    return m.group(1) if m else None


def _ensure_latest_qr_png(save_root: Path, url: str) -> Path | None:
    """
    URL から QR PNG を生成して保存し、保存先パスを返す。
    生成できない（依存不足等）場合は None。
    """
    try:
        import qrcode  # type: ignore
    except Exception:
        return None

    img_dir = save_root / ".images"
    img_dir.mkdir(parents=True, exist_ok=True)

    ts = time.time()
    out_path = img_dir / f"qr_{ts:.6f}.png"
    # URL も同じ場所に保存（後から内容確認できるように）
    (img_dir / "qr_latest_url.txt").write_text(url + "\n", encoding="utf-8")
    qr = qrcode.QRCode(border=2)
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    img.save(out_path)
    return out_path


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
    saw_native_img = False
    seen_urls: list[str] = []
    try:
        for chunk in cl.requestSQR3(isSelf=True):
            text = str(chunk)
            # URL / QR画像パス / PIN表示だけ標準出力に出す（token 本文は出さない）。
            if text.startswith(("URL:", "IMG:", "請輸入pincode:")):
                print(text)
            if "IMG:" in text:
                # CHRLINE 側が画像を生成できているなら、自前生成は不要（重複防止）
                saw_native_img = True
            # URL しか出ない環境でも、こちらで QR 画像を生成して IMG: を出す
            url = _extract_login_url_from_chunk_text(text)
            if url:
                seen_urls.append(url)
    finally:
        cleanup_chrline_qr_images(p)

    if (not saw_native_img) and seen_urls:
        # secret 付きURLを優先（LINE側で有効なことが多い）
        uniq = list(dict.fromkeys(seen_urls))
        best = next((u for u in uniq if "secret=" in u), uniq[-1])
        print(f"URL: {best}")
        png = _ensure_latest_qr_png(p, best)
        if png is not None:
            print(f"IMG: {png}")

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
