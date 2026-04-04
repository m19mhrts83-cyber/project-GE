# -*- coding: utf-8 -*-
"""
215 の Gmail 連携で共用する OAuth スコープ。

mail_automation/send_mail.py だけ gmail.send に限定すると、
token.json の保存・更新のたびに認可が送信専用に寄り、
gmail_to_yoritoori / yoritoori_send 等が 403 insufficient authentication scopes になる。
常にこのリストで Credentials を構築・保存すること。
"""

from __future__ import annotations

import json
from pathlib import Path

GMAIL_SCOPES_215 = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/gmail.send",
]


def granted_scopes_from_token_record(d: dict) -> set[str]:
    """token.json 等の辞書から付与済みスコープ集合を取り出す。"""
    g = d.get("scopes")
    if isinstance(g, str) and g.strip():
        return set(g.split())
    if isinstance(g, list):
        return set(g)
    raw = d.get("scope")
    if isinstance(raw, str) and raw.strip():
        return set(raw.split())
    return set()


def token_satisfies_215_scopes(d: dict) -> bool:
    """215 共通スコープが token 記録にすべて含まれるか（send のみ等で欠ける場合は False）。"""
    granted = granted_scopes_from_token_record(d)
    if not granted:
        return False
    return set(GMAIL_SCOPES_215).issubset(granted)


def _token_file_satisfies_215(path: Path) -> bool:
    if not path.is_file():
        return False
    try:
        d = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return False
    return token_satisfies_215_scopes(d)


def resolve_single_token_path_215(
    manual_dir: Path,
    candidate: Path,
    *,
    explicit_via_env: bool,
) -> Path:
    """
    送信・税理士取得など単一 Gmail クライアント用の token パス。
    GMAIL_TOKEN_PATH で明示していないとき、candidate（通常 token.json）が 215 未満なら
    同フォルダの token_estate.json / token_m19m.json のうち、最初に 215 を満たすものを使う。
    """
    if explicit_via_env:
        return candidate
    order = [
        candidate,
        manual_dir / "token_estate.json",
        manual_dir / "token_m19m.json",
    ]
    seen: set[Path] = set()
    for p in order:
        try:
            rp = p.resolve()
        except Exception:
            rp = p
        if rp in seen:
            continue
        seen.add(rp)
        if _token_file_satisfies_215(p):
            return p
    return candidate
