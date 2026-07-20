# -*- coding: utf-8 -*-
"""215 神大家 — Google Sheets / Drive 連携用 OAuth スコープ（estate アカウント）."""

from __future__ import annotations

# 課題提出状況の読取 + Drive 上のフォルダ参照・今後の申込書アップロード
GOOGLE_WORKSPACE_SCOPES_ESTATE = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.readonly",
    "https://www.googleapis.com/auth/drive.file",
]

DEFAULT_LOGIN_HINT = "matsuno.estate@gmail.com"
DEFAULT_TOKEN_NAME = "token_google_workspace_estate.json"
