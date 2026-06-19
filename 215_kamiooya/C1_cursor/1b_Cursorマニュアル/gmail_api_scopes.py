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


def resolve_token_path_215(
    manual_dir: Path,
    candidate: Path,
    *,
    explicit_via_env: bool,
    purpose: str = "send",
) -> Path:
    """
    単一 Gmail クライアント用の token パス。

    purpose:
      - send: パートナー送信など。個人 Gmail（estate / m19m）を優先（相手に届く From を維持）
      - receive: 取り込み。admin@（livingsupport）を優先
    """
    if explicit_via_env:
        return candidate
    if purpose == "receive":
        order = [
            manual_dir / "token_livingsupport.json",
            candidate,
            manual_dir / "token_estate.json",
            manual_dir / "token_m19m.json",
            manual_dir / "token_chk59.json",
        ]
    else:
        order = [
            candidate,
            manual_dir / "token_estate.json",
            manual_dir / "token_m19m.json",
            manual_dir / "token_chk59.json",
            manual_dir / "token_livingsupport.json",
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


def resolve_single_token_path_215(
    manual_dir: Path,
    candidate: Path,
    *,
    explicit_via_env: bool,
) -> Path:
    """送信・単一クライアント用（個人 Gmail 優先）。後方互換の別名。"""
    return resolve_token_path_215(
        manual_dir,
        candidate,
        explicit_via_env=explicit_via_env,
        purpose="send",
    )


def resolve_receive_token_path_215(
    manual_dir: Path,
    candidate: Path,
    *,
    explicit_via_env: bool,
) -> Path:
    """取り込み用（admin@ 優先）。"""
    return resolve_token_path_215(
        manual_dir,
        candidate,
        explicit_via_env=explicit_via_env,
        purpose="receive",
    )
