"""WeStudy 認証情報の共通ロード（神大家さん倶楽部 自動化）."""

from __future__ import annotations

import os
from pathlib import Path

# 正本: OneDrive 上の Q&A チャットボット scripts/.env（既存の WESTUDY_USER / WESTUDY_PASS）
_DEFAULT_ENV_FILE = Path(
    "/Users/matsunomasaharu2/Library/CloudStorage/OneDrive-個人用/215_神・大家さん倶楽部"
    "/C1_cursor/1c_神・大家さん倶楽部_AI推進/神・大家さん倶楽部情報Q&Aチャットボット/scripts/.env"
)

DEFAULT_LOGIN_URL = "https://westudy.co.jp/login"
DEFAULT_FORUM_URL = "https://westudy.co.jp/course/kami-ooyasan-club?t=forums"


def westudy_env_file() -> Path:
    """WeStudy 認証 .env のパス（WESTUDY_ENV_FILE で上書き可）。"""
    override = (os.environ.get("WESTUDY_ENV_FILE") or "").strip()
    if override:
        return Path(override).expanduser().resolve()
    return _DEFAULT_ENV_FILE


def load_westudy_env(*, force: bool = False) -> Path:
    """
    WESTUDY_USER / WESTUDY_PASS 等を環境変数へ読み込む。
    戻り値: 読み込んだ .env のパス。
    """
    env_path = westudy_env_file()
    if not env_path.is_file():
        raise FileNotFoundError(
            f"WeStudy 認証ファイルがありません: {env_path}\n"
            "scripts/.env.example をコピーして WESTUDY_USER / WESTUDY_PASS を設定してください。"
        )

    if force or not os.environ.get("WESTUDY_USER") or not os.environ.get("WESTUDY_PASS"):
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value

    _validate_credentials()
    return env_path


def _validate_credentials() -> None:
    user = (os.environ.get("WESTUDY_USER") or "").strip()
    pw = (os.environ.get("WESTUDY_PASS") or "").strip()
    if not user or not pw:
        raise RuntimeError(
            "WESTUDY_USER / WESTUDY_PASS が未設定です。"
            f" {westudy_env_file()} を確認してください。"
        )
    if user == "your-westudy-login-id" or pw == "your-westudy-login-password":
        raise RuntimeError(
            "WESTUDY_USER / WESTUDY_PASS が .env.example のダミー値のままです。"
            f" {westudy_env_file()} を実値で保存してください。"
        )


def westudy_login_url() -> str:
    return (os.environ.get("WESTUDY_LOGIN_URL") or "").strip() or DEFAULT_LOGIN_URL


def westudy_forum_url() -> str:
    return (os.environ.get("WESTUDY_FORUM_URL") or "").strip() or DEFAULT_FORUM_URL
