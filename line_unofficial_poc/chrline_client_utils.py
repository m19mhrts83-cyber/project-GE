"""
CHRLINE-PatchV2 用: .line_auth から保存トークンを読み、QR なしでクライアントを起動する。

トークン文字列はログに出さない。ファイルは LINE_UNOFFICIAL_AUTH_DIR/.tokens/ 配下。
CHRLINE は QR 初回ログイン時に .tokens を自動作成しないことがあるため、
chrline_qr_login_poc 成功後に persist_auth_token を呼ぶ。

環境変数:
  LINE_CHRLINE_AUTO_OPEN_QR … 1/true/yes のときだけ、再認証時に QR 画像を OS で自動表示する。
    未設定時は自動表示しない（ターミナルに IMG: パスが出るので、必要なら手動で開く）。
    LINE 側がセッションを切ったときの QR 認証そのものは非公式 API の制約で省略できない。

  LINE_UNOFFICIAL_AUTH_DIR … 未設定時は line_unofficial_poc 直下の .line_auth_local（ローカル固定・Git 対象外）。
    クラウド同期パスを明示指定した場合は警告を出す。
"""
from __future__ import annotations

import os
import subprocess
import sys
from hashlib import md5
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
_DEFAULT_LOCAL_AUTH_DIR = (ROOT / ".line_auth_local").resolve()
_CLOUD_PATH_HINTS = (
    "OneDrive",
    "Google Drive",
    "GoogleDrive",
    "Dropbox",
    "iCloud",
    "Box Sync",
)
load_dotenv(ROOT / ".env")


def cleanup_chrline_qr_images(save_root: Path) -> None:
    """
    CHRLINE が savePath/.images に保存する qr_*.png を削除する（容量用）。
    認証完了後・各実行の最初でも呼ぶ。
    """
    d = save_root / ".images"
    if not d.is_dir():
        return
    for f in d.glob("qr_*.png"):
        try:
            f.unlink()
        except OSError:
            pass
    try:
        next(d.iterdir())
    except StopIteration:
        try:
            d.rmdir()
        except OSError:
            pass
    except OSError:
        pass


def save_root_from_env() -> Path:
    raw = os.environ.get("LINE_UNOFFICIAL_AUTH_DIR", "").strip()
    if raw:
        p = Path(raw).expanduser().resolve()
    else:
        p = _DEFAULT_LOCAL_AUTH_DIR
        os.environ["LINE_UNOFFICIAL_AUTH_DIR"] = str(p)
    p.mkdir(parents=True, exist_ok=True)
    s = str(p)
    if any(h in s for h in _CLOUD_PATH_HINTS):
        print(
            "警告: LINE_UNOFFICIAL_AUTH_DIR がクラウド同期フォルダ付近です。"
            "セッション競合で QR が増えやすいため、"
            f"未設定時のローカル既定 {_DEFAULT_LOCAL_AUTH_DIR} への切り替え（.tokens 等をコピー）を推奨します。",
            file=sys.stderr,
        )
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


def _env_truthy(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in ("1", "true", "yes", "on")


def _open_qr_image_if_possible(img_path: str) -> None:
    """失効時の再認証で生成された QR 画像を開く（LINE_CHRLINE_AUTO_OPEN_QR があるときのみ）。"""
    if not _env_truthy("LINE_CHRLINE_AUTO_OPEN_QR"):
        return
    p = (img_path or "").strip()
    if not p:
        return
    try:
        if sys.platform == "darwin":
            subprocess.run(["open", p], check=False)
        elif sys.platform.startswith("linux"):
            subprocess.run(["xdg-open", p], check=False)
        elif os.name == "nt":
            os.startfile(p)  # type: ignore[attr-defined]
    except Exception:
        # 開けない環境でも再認証自体は続行する。
        pass


def load_latest_saved_token(save_root: Path) -> str | None:
    tokens = load_saved_tokens_newest_first(save_root)
    return tokens[0] if tokens else None


def load_saved_tokens_newest_first(save_root: Path) -> list[str]:
    """`.tokens` 内の全ファイルを更新日時の新しい順に読み、有効な文字列のみ重複排除して返す。"""
    d = save_root / ".tokens"
    if not d.is_dir():
        return []
    files = [f for f in d.iterdir() if f.is_file()]
    if not files:
        return []
    files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    out: list[str] = []
    seen: set[str] = set()
    for f in files:
        t = f.read_text(encoding="utf-8", errors="replace").strip()
        if len(t) < 30 or t in seen:
            continue
        seen.add(t)
        out.append(t)
    return out


def build_logged_in_client(save_root: Path):
    """保存済み authToken で CHRLINE を初期化。失効時はQR再認証で復旧する。"""
    from CHRLINE import CHRLINE
    from CHRLINE.exceptions import LineServiceException

    cleanup_chrline_qr_images(save_root)

    def _is_logged_out(e: LineServiceException) -> bool:
        return "V3_TOKEN_CLIENT_LOGGED_OUT" in str(e)

    for token in load_saved_tokens_newest_first(save_root):
        try:
            cl = CHRLINE(
                token,
                device="DESKTOPWIN",
                useThrift=True,
                savePath=str(save_root),
            )
        except LineServiceException as e:
            if not _is_logged_out(e):
                raise
            continue
        try:
            cl.initAll()
        except LineServiceException as e:
            if not _is_logged_out(e):
                raise
            continue
        return cl

    print(
        "保存トークンが無効なため、QR再認証を開始します（LINEアプリで承認してください）。",
        file=sys.stderr,
    )
    cl = CHRLINE(device="DESKTOPWIN", useThrift=True, savePath=str(save_root), noLogin=True)
    try:
        for chunk in cl.requestSQR3(isSelf=True):
            text = str(chunk)
            if text.startswith(("URL:", "IMG:", "請輸入pincode:")):
                print(text)
            if text.startswith("IMG:"):
                _open_qr_image_if_possible(text.removeprefix("IMG:").strip())
        refreshed = (getattr(cl, "authToken", None) or "").strip()
        if not refreshed:
            print("エラー: QR再認証でトークン取得に失敗しました。", file=sys.stderr)
            sys.exit(1)
        persist_auth_token(save_root, refreshed)
        cl.initAll()
        return cl
    finally:
        cleanup_chrline_qr_images(save_root)
