#!/usr/bin/env python3
"""Supabase PostgREST / Free 枠エラーの共通判定。

HTTP 402 exceed_egress_quota はリトライしても復旧しない。
GHA では即座に明確な ::error:: で止め、pydantic の二次 ValidationError を出さない。
"""
from __future__ import annotations

import sys
from typing import Any


EXIT_QUOTA = 6


def _exc_blob(exc: BaseException | Any) -> str:
    parts: list[str] = [str(exc)]
    if isinstance(exc, dict):
        parts.append(str(exc))
    for attr in ("message", "code", "details", "hint", "args"):
        try:
            v = getattr(exc, attr, None)
        except Exception:
            v = None
        if v is not None:
            parts.append(str(v))
    return " ".join(parts).lower()


def is_supabase_quota_error(exc: BaseException | Any) -> bool:
    """Free 枠超過（egress 等）による制限か。"""
    blob = _exc_blob(exc)
    if "exceed_egress_quota" in blob or "egress_quota" in blob:
        return True
    if "402" in blob and (
        "restricted" in blob or "spend cap" in blob or "upgrade their plan" in blob
    ):
        return True
    # postgrest APIError が code=402 を持つ場合
    code = getattr(exc, "code", None)
    if code is None and isinstance(exc, dict):
        code = exc.get("code")
    try:
        if int(code) == 402:
            return True
    except (TypeError, ValueError):
        pass
    return False


def quota_error_message(exc: BaseException | Any | None = None) -> str:
    detail = ""
    if exc is not None:
        blob = _exc_blob(exc)
        if "egress" in blob:
            detail = "（exceed_egress_quota）"
    return (
        "Supabase がプラン上限超過で制限中（HTTP 402）"
        f"{detail}。"
        "リトライでは復旧しない。Dashboard の Usage を確認し、"
        "請求サイクル更新・使用量削減・spend cap 解除を待つ。"
    )


def abort_on_quota(exc: BaseException | Any, *, stream=sys.stderr) -> None:
    """quota なら ::error:: を出して SystemExit(6)。違うなら何もしない。"""
    if not is_supabase_quota_error(exc):
        return
    msg = quota_error_message(exc)
    print(f"::error::{msg}", file=stream)
    print(f"SUMMARY: supabase_quota reason=egress_or_plan", file=stream)
    raise SystemExit(EXIT_QUOTA)
