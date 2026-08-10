"""
状況ウォッチ汎用 user_ack（確認した → バッジ抑制）の指紋・マージ。

Dashboard lib/watchUserAck.ts と仕様を揃える。
"""
from __future__ import annotations

import os
import re
from datetime import datetime, timedelta, timezone
from typing import Any


def quiet_days() -> int:
    raw = (os.environ.get("JARVIS_WATCH_ACK_QUIET_DAYS") or "").strip()
    try:
        n = int(raw) if raw else 7
    except ValueError:
        n = 7
    return max(1, n)


def _as_dict(v: Any) -> dict[str, Any]:
    return v if isinstance(v, dict) else {}


def normalize_summary_for_ack(summary: str | None) -> str:
    s = str(summary or "").strip()
    s = re.sub(r"約\s*\d+\s*時間前", "時間前", s)
    s = re.sub(r"\d+\s*時間前", "時間前", s)
    s = re.sub(r"約\s*\d+\s*日前", "日前", s)
    s = re.sub(r"\d+\s*日前", "日前", s)
    s = re.sub(r"あと\s*\d+\s*日", "あとN日", s)
    s = re.sub(r"残り\s*\d+\s*日", "残りN日", s)
    s = re.sub(r"\d{4}-\d{2}-\d{2}T[\d:+.-]+", "TS", s)
    s = re.sub(r"\d{4}/\d{2}/\d{2}\s+\d{2}:\d{2}", "DT", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s[:120]


def build_openchat_fingerprint(payload: dict[str, Any], level: str | None = None) -> str:
    rem = _as_dict(payload.get("remediation"))
    mf = _as_dict(payload.get("main_freshness"))
    watch = _as_dict(payload.get("watch"))
    worst = str(payload.get("worst_level") or level or "").strip()
    symptom = str(rem.get("symptom") or "").strip()
    main_stale = bool(mf.get("stale") or rem.get("main_stale") or payload.get("main_stale"))
    write_err = bool(payload.get("last_write_error") or watch.get("last_write_error"))
    routes = payload.get("routes") if isinstance(payload.get("routes"), list) else []
    attention_ids = sorted(
        str(r.get("route_id") or "").strip()
        for r in routes
        if isinstance(r, dict) and r.get("level") == "attention" and r.get("route_id")
    )
    return "|".join(
        [
            "openchat",
            worst,
            symptom,
            "main1" if main_stale else "main0",
            "err1" if write_err else "err0",
            ",".join(attention_ids),
        ]
    )


def build_generic_fingerprint(watch_id: str, level: str | None, summary: str | None) -> str:
    sum120 = normalize_summary_for_ack(summary)
    return "|".join(["watch", str(watch_id or "").strip(), str(level or "").strip(), sum120])


def build_fingerprint(
    watch_id: str,
    *,
    level: str | None,
    summary: str | None,
    payload: dict[str, Any] | None,
) -> str:
    pl = payload if isinstance(payload, dict) else {}
    if watch_id == "openchat_threads":
        return build_openchat_fingerprint(pl, level)
    return build_generic_fingerprint(watch_id, level, summary)


def parse_iso(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def is_ack_active(
    user_ack: dict[str, Any] | None,
    current_fingerprint: str,
    *,
    now: datetime | None = None,
) -> bool:
    if not isinstance(user_ack, dict):
        return False
    fp = str(user_ack.get("fingerprint") or "")
    if not fp or fp != str(current_fingerprint):
        return False
    until = parse_iso(str(user_ack.get("quiet_until") or "") or None)
    if until is None:
        return False
    now_dt = now or datetime.now(timezone.utc)
    if now_dt.tzinfo is None:
        now_dt = now_dt.replace(tzinfo=timezone.utc)
    return now_dt < until.astimezone(timezone.utc)


def merge_user_ack_into_payload(
    watch_id: str,
    payload: dict[str, Any],
    *,
    level: str | None,
    summary: str | None,
    remote_payload: dict[str, Any] | None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """
    remote の user_ack を優先マージ。
    指紋一致かつ quiet_until 前 → show_banner=false / badge_suppressed。
    不一致または期限切れ → user_ack を落として通常の show_banner に戻す。
    """
    out = dict(payload)
    remote = remote_payload if isinstance(remote_payload, dict) else {}
    remote_ack = remote.get("user_ack") if isinstance(remote.get("user_ack"), dict) else None
    local_ack = out.get("user_ack") if isinstance(out.get("user_ack"), dict) else None
    # remote 優先（Dashboard で押した確認を Mac push で潰さない）
    candidate = remote_ack or local_ack
    fp = build_fingerprint(watch_id, level=level, summary=summary, payload=out)
    if is_ack_active(candidate, fp, now=now):
        out["user_ack"] = candidate
        out["show_banner"] = False
        out["badge_suppressed"] = True
    else:
        out.pop("user_ack", None)
        out.pop("badge_suppressed", None)
        # show_banner は呼び出し側が既に設定していれば維持。未設定なら level から
        if "show_banner" not in out:
            out["show_banner"] = str(level or "") in ("attention", "warn")
    return out


def make_user_ack(fingerprint: str, *, days: int | None = None) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    d = days if days is not None else quiet_days()
    until = now + timedelta(days=max(1, d))
    return {
        "fingerprint": fingerprint,
        "acked_at": now.isoformat(timespec="seconds"),
        "quiet_until": until.isoformat(timespec="seconds"),
    }
