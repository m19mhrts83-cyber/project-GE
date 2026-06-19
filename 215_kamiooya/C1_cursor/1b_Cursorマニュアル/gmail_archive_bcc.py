# -*- coding: utf-8 -*-
"""
個人 Gmail から送信したメールを admin@livingsupport-matsu.co.jp に BCC 控えする。

環境変数:
  GMAIL_ARCHIVE_BCC          控え先（未設定時: admin@livingsupport-matsu.co.jp）
  GMAIL_ARCHIVE_BCC_DISABLE  1/true/yes で無効化
  GMAIL_ARCHIVE_BCC_SOURCES  カンマ区切りで BCC 対象の送信元アドレス（未設定時は下記既定2件）
"""

from __future__ import annotations

import os
from email.utils import getaddresses

DEFAULT_ARCHIVE_BCC = "admin@livingsupport-matsu.co.jp"
DEFAULT_SOURCE_ACCOUNTS = frozenset(
    {
        "matsuno.estate@gmail.com",
        "m19m.hrts83@gmail.com",
    }
)


def archive_bcc_disabled() -> bool:
    return os.environ.get("GMAIL_ARCHIVE_BCC_DISABLE", "").strip().lower() in (
        "1",
        "true",
        "yes",
    )


def archive_bcc_address() -> str:
    return os.environ.get("GMAIL_ARCHIVE_BCC", DEFAULT_ARCHIVE_BCC).strip()


def archive_bcc_source_accounts() -> set[str]:
    raw = os.environ.get("GMAIL_ARCHIVE_BCC_SOURCES", "").strip()
    if raw:
        return {a.strip().lower() for a in raw.split(",") if a.strip()}
    return set(DEFAULT_SOURCE_ACCOUNTS)


def apply_archive_bcc(msg, sender_email: str | None) -> bool:
    """
    個人 Gmail からの送信時、msg に Bcc 控えを付与する。
    付与した場合 True。
    """
    if archive_bcc_disabled():
        return False
    sender = (sender_email or "").strip().lower()
    if not sender or sender not in archive_bcc_source_accounts():
        return False
    bcc = archive_bcc_address()
    if not bcc:
        return False

    existing = (msg.get("Bcc") or "").strip()
    addrs = {addr.lower() for _, addr in getaddresses([existing, bcc]) if addr}
    if not addrs:
        return False
    msg["Bcc"] = ", ".join(sorted(addrs))
    return True
