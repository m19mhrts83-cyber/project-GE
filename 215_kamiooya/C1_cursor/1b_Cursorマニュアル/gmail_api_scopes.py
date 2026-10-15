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


def token_satisfies_scopes(d: dict, required: list[str] | tuple[str, ...]) -> bool:
    """required がすべて token 記録に含まれるか。"""
    granted = granted_scopes_from_token_record(d)
    if not granted:
        return False
    return set(required).issubset(granted)


def token_satisfies_215_scopes(d: dict) -> bool:
    """215 共通スコープが token 記録にすべて含まれるか（send のみ等で欠ける場合は False）。"""
    return token_satisfies_scopes(d, GMAIL_SCOPES_215)


GMAIL_SCOPES_READ_MODIFY = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.modify",
]


def token_satisfies_read_modify_scopes(d: dict) -> bool:
    """Gmail 読取・ラベル変更のみ（MailGates 等）。send 欠如でも可。"""
    return token_satisfies_scopes(d, GMAIL_SCOPES_READ_MODIFY)


GMAIL_SCOPES_READONLY = [
    "https://www.googleapis.com/auth/gmail.readonly",
]

# Gmail API のスコープだけを識別（Drive/Calendar 等は合流させない）
GMAIL_SCOPE_PREFIX = "https://www.googleapis.com/auth/gmail."


def gmail_scopes_only(scopes: set[str] | list[str] | tuple[str, ...]) -> set[str]:
    """gmail.* スコープだけを残す（include_granted_scopes 相当の混入を避ける）。"""
    out: set[str] = set()
    for s in scopes:
        s = (s or "").strip()
        if s.startswith(GMAIL_SCOPE_PREFIX):
            out.add(s)
    return out


def resolve_scopes_for_oauth_flow(
    required: list[str] | tuple[str, ...],
    existing_record: dict | None = None,
) -> list[str]:
    """再同意フローに渡すスコープ。

    既存 token に付いていた gmail.*（特に send）を落とさないよう、
    required と既存 Gmail スコープの和集合を返す。
    Drive/Calendar 等は含めない。
    """
    merged = gmail_scopes_only(required)
    if existing_record:
        merged |= gmail_scopes_only(granted_scopes_from_token_record(existing_record))
    # 安定した並び（215 既知順 → その他）
    known_order = list(GMAIL_SCOPES_215)
    ordered = [s for s in known_order if s in merged]
    ordered.extend(sorted(merged - set(ordered)))
    return ordered or list(required)


def merge_gmail_scopes_for_persist(
    creds_json: str,
    *,
    existing_token_path: Path | None = None,
    existing_record: dict | None = None,
) -> str:
    """token 保存直前に、既存の gmail.* スコープ（特に send）を落さない。

    include_granted_scopes は付けない方針のまま、JSON 上の scopes だけ合流する。
    再同意フロー側は resolve_scopes_for_oauth_flow で実グラントも合流すること。
    """
    try:
        data = json.loads(creds_json)
    except (json.JSONDecodeError, TypeError):
        return creds_json

    existing = existing_record
    if existing is None and existing_token_path is not None:
        path = Path(existing_token_path)
        if path.is_file():
            try:
                existing = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                existing = None

    new_scopes = gmail_scopes_only(granted_scopes_from_token_record(data))
    old_scopes = gmail_scopes_only(granted_scopes_from_token_record(existing or {}))
    merged = new_scopes | old_scopes
    if not merged:
        return creds_json

    known_order = list(GMAIL_SCOPES_215)
    ordered = [s for s in known_order if s in merged]
    ordered.extend(sorted(merged - set(ordered)))
    data["scopes"] = ordered
    # 一部ライブラリは space 区切り scope も見る
    if "scope" in data and isinstance(data.get("scope"), str):
        data["scope"] = " ".join(ordered)
    return json.dumps(data)


def resolve_read_scopes_for_token(d: dict) -> list[str]:
    """読み取り専用の取込で使う最小スコープ。

    取込・LINE公式エクスポートは読み取りしかしないため、modify を持たない
    token（estate が readonly 単独など）でもブラウザ再同意なしで動かす。
    """
    if token_satisfies_read_modify_scopes(d):
        return list(GMAIL_SCOPES_READ_MODIFY)
    if token_satisfies_scopes(d, GMAIL_SCOPES_READONLY):
        return list(GMAIL_SCOPES_READONLY)
    return list(GMAIL_SCOPES_READ_MODIFY)


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
