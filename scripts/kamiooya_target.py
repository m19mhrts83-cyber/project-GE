"""神大家 AI ナビ（kamiooya-qa）の Supabase 接続先を 1 か所で決める（2026-11-20）。

東京リージョンへの移設に備え、プロジェクト ref の直書きをここへ集める。
切替は環境変数 KAMIOOYA_PROJECT_REF を新しい ref にするだけ（未設定なら東京）。
鍵は扱わない。URL だけを返す。
"""
from __future__ import annotations

import os
import re

# 東京（ap-northeast-1）。2026-11-21 にムンバイから移設、旧は 11-24 に削除。
DEFAULT_REF = "sufbsyddqgekvcgadhpv"
_REF_RE = re.compile(r"^[a-z0-9]{20}$")


def project_ref() -> str:
    ref = (os.environ.get("KAMIOOYA_PROJECT_REF") or DEFAULT_REF).strip()
    if not _REF_RE.fullmatch(ref):
        raise ValueError("KAMIOOYA_PROJECT_REF は Supabase の ref（英小文字・数字20桁）で指定してください")
    return ref


def base_url(ref: str | None = None) -> str:
    return f"https://{ref or project_ref()}.supabase.co"


def storage_url(ref: str | None = None) -> str:
    return f"https://{ref or project_ref()}.storage.supabase.co"


def functions_url(name: str, ref: str | None = None) -> str:
    return f"{base_url(ref)}/functions/v1/{name}"


def is_target_url(url: str) -> bool:
    """書き込み前の取り違え防止: 渡された SUPABASE_URL が今の接続先か。"""
    return (url or "").rstrip("/") == base_url()


def rewrite(text: str) -> str:
    """公開物（Raimo の app.js / API 定義）に残る現行 ref を今の接続先へ置き換える。"""
    ref = project_ref()
    if ref == DEFAULT_REF:
        return text
    return text.replace(f"https://{DEFAULT_REF}.", f"https://{ref}.")
