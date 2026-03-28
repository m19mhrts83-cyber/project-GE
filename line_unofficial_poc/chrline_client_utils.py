"""
CHRLINE-PatchV2 用: .line_auth から保存トークンを読み、QR なしでクライアントを起動する。

トークン文字列はログに出さない。ファイルは LINE_UNOFFICIAL_AUTH_DIR/.tokens/ 配下。
CHRLINE は QR 初回ログイン時に .tokens を自動作成しないことがあるため、
chrline_qr_login_poc 成功後に persist_auth_token を呼ぶ。
"""
from __future__ import annotations

import os
import sys
from hashlib import md5
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")


def save_root_from_env() -> Path:
    raw = os.environ.get("LINE_UNOFFICIAL_AUTH_DIR", "").strip()
    if not raw:
        print(
            "エラー: .env の LINE_UNOFFICIAL_AUTH_DIR を設定してください。",
            file=sys.stderr,
        )
        sys.exit(1)
    p = Path(raw)
    p.mkdir(parents=True, exist_ok=True)
    return p


def persist_auth_token(save_root: Path, auth_token: str) -> None:
    """
    CHRLINE の checkNextToken / handleNextToken と同じ規則で 1 ファイル保存する。
    auth_token はログに出さない。
    """
    t = (auth_token or "").strip()
    if len(t) < 8:
        return
    d = save_root / ".tokens"
    d.mkdir(parents=True, exist_ok=True)
    fn = md5(t.encode()).hexdigest()
    (d / fn).write_text(t, encoding="utf-8")


def load_latest_saved_token(save_root: Path) -> str | None:
    d = save_root / ".tokens"
    if not d.is_dir():
        return None
    files = [f for f in d.iterdir() if f.is_file()]
    if not files:
        return None
    files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    t = files[0].read_text(encoding="utf-8", errors="replace").strip()
    return t if len(t) > 30 else None


def build_logged_in_client(save_root: Path):
    """保存済み authToken で CHRLINE を初期化（ログイン済み想定）。"""
    from CHRLINE import CHRLINE

    token = load_latest_saved_token(save_root)
    if not token:
        print(
            "エラー: 保存トークンがありません。先に chrline_qr_login_poc.py で QR ログインしてください。",
            file=sys.stderr,
        )
        sys.exit(1)
    return CHRLINE(
        token,
        device="DESKTOPWIN",
        useThrift=True,
        savePath=str(save_root),
    )
