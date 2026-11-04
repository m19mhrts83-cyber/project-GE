#!/usr/bin/env python3
"""人が書いたメールか（返信が要りそうか）を LLM なしで見分ける。

一般メールの要対応は、ほとんどがカード会社・銀行・メルマガ・通知の自動送信だった
（2026-11-04 実測: 直近120通のうち人が書いたものは5通程度）。依頼語（「ご確認」「お願い」）は
自動送信にも必ず入るので、送り手と書き方で判定する。

人が書いた ＝ 一括配信の印が無く、次のいずれか:
  1. 件名が RE:/Re:/返信: で始まる（やり取りの続き）
  2. 送信元が携帯・フリーメール
  3. 冒頭で「松野様」と宛名があり、件名にブランド見出し【…】が無い
  4. 送信元の名前部分が個人名らしく（role 語でない）、冒頭に宛名がある
"""
from __future__ import annotations

import re

BULK_BODY_RE = re.compile(
    r"(配信停止|配信解除|送信専用|返信できません|返信いただいても|ご返信いただいても|"
    r"unsubscribe|メールマガジン|メルマガ|配信元|受信設定|配信を希望されない|"
    r"オプトアウト|このメールアドレスは送信のみ)",
    re.I,
)
REPLY_SUBJECT_RE = re.compile(r"^\s*(re|ｒｅ|返信)\s*[:：]", re.I)
BRAND_SUBJECT_RE = re.compile(r"【[^】]{2,40}】")
ADDRESSED_RE = re.compile(r"松野\s*(真治)?\s*(様|さま|さん)")
FREE_MAIL_RE = re.compile(
    r"@(ezweb\.ne\.jp|docomo\.ne\.jp|softbank\.ne\.jp|i\.softbank\.jp|au\.com|"
    r"gmail\.com|icloud\.com|me\.com|outlook\.(com|jp)|hotmail\.(com|co\.jp)|"
    r"yahoo\.co\.jp|ymail\.ne\.jp)$",
    re.I,
)
# 窓口・システム送信の名前部分
ROLE_TOKENS = {
    "info", "information", "support", "mail", "noreply", "no", "reply", "notice",
    "notification", "notifications", "news", "newsletter", "team", "service",
    "statement", "post", "master", "postmaster", "campaign", "matching", "official",
    "customer", "customers", "center", "web", "mobile", "welcome", "invoice",
    "statements", "action", "office", "account", "accounts", "desk", "admin",
    "sales", "contact", "direct", "help", "system", "staff", "member", "members",
    "store", "shop", "order", "orders", "billing", "press", "pr", "marketing",
}

def _addr(from_email: str) -> str:
    s = str(from_email or "").strip()
    m = re.search(r"<([^>]+)>", s)
    if m:
        s = m.group(1)
    return s.strip().lower()


def _local_tokens(addr: str) -> list[str]:
    local = addr.split("@", 1)[0]
    local = local.split("+", 1)[0]
    return [t for t in re.split(r"[._\-]+", local) if t]


def looks_personal_local(addr: str) -> bool:
    """yokoi_yutaka / to-sirai / taro.yamada のような個人名らしい名前部分。"""
    toks = _local_tokens(addr)
    if not toks or any(t in ROLE_TOKENS or re.sub(r"\d+$", "", t) in ROLE_TOKENS for t in toks):
        return False
    return len(toks) >= 2 and all(t.isalpha() for t in toks)


def is_bulk_mail(body: str) -> bool:
    return bool(BULK_BODY_RE.search(str(body or "")))


def looks_human_mail(from_email: str, subject: str, body: str) -> bool:
    body = str(body or "")
    subject = str(subject or "")
    if is_bulk_mail(body):
        return False
    addr = _addr(from_email)
    head = body[:400]
    addressed = bool(ADDRESSED_RE.search(head))
    if REPLY_SUBJECT_RE.search(subject):
        return True
    if FREE_MAIL_RE.search(addr):
        return True
    branded = bool(BRAND_SUBJECT_RE.search(subject))
    if addressed and not branded:
        return True
    if addressed and looks_personal_local(addr):
        return True
    return False
