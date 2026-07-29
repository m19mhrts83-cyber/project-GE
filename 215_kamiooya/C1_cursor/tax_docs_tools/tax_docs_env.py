"""税理士提出ツール共通: 認証の正本は .env.jarvis_private、互換で .env.tax_docs。"""

from __future__ import annotations

import os
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_TAX_DOCS_ENV = SCRIPT_DIR / ".env.tax_docs"
JARVIS_PRIVATE_ENV = Path.home() / "git-repos" / ".env.jarvis_private"


def load_env_file(path: Path) -> None:
    """未設定キーのみ .env から os.environ へ載せる。"""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'\"")
        if key and value and key not in os.environ:
            os.environ[key] = value


def load_tax_credentials(env_file: str | Path | None = None) -> None:
    """
    優先: ~/git-repos/.env.jarvis_private
    次: env_file（既定 tax_docs_tools/.env.tax_docs）
    """
    load_env_file(JARVIS_PRIVATE_ENV)
    fallback = Path(env_file) if env_file else DEFAULT_TAX_DOCS_ENV
    load_env_file(fallback)
