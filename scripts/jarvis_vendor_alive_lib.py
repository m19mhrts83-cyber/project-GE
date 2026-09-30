"""業者リスト横断 — 生存確認（alive_*）共通ロジック。

種別の既定周期:
  repair 90日 / re（物件紹介）・mgmt（管理会社）180日

CLI 例は各 list スクリプトの --mark-alive / --alive-queue、
および scripts/jarvis_vendor_alive_web_check.py を参照。
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

ALIVE_STATUSES = frozenset({"unknown", "ok", "fail", "stale"})
ALIVE_METHODS = frozenset({"web", "phone", "both", ""})

# kind → 期限日数
DEFAULT_DUE_DAYS: dict[str, int] = {
    "re": 180,
    "repair": 90,
    "mgmt": 180,
}


def today_iso() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def parse_date(val: Any) -> date | None:
    if not val:
        return None
    s = str(val).strip()[:10]
    if not s:
        return None
    try:
        return date.fromisoformat(s)
    except ValueError:
        return None


def due_days_for(v: dict[str, Any], *, kind: str) -> int:
    raw = v.get("alive_due_days")
    if raw is not None and str(raw).strip() != "":
        try:
            return max(1, int(raw))
        except (TypeError, ValueError):
            pass
    return DEFAULT_DUE_DAYS.get(kind, 180)


def days_since_checked(v: dict[str, Any], *, today: date | None = None) -> int | None:
    d = parse_date(v.get("alive_checked_at"))
    if not d:
        return None
    t = today or date.today()
    return (t - d).days


def is_overdue(v: dict[str, Any], *, kind: str, today: date | None = None) -> bool:
    days = days_since_checked(v, today=today)
    if days is None:
        return True  # 未確認は期限切れ扱い（キュー優先）
    return days >= due_days_for(v, kind=kind)


def effective_alive_status(v: dict[str, Any], *, kind: str, today: date | None = None) -> str:
    """表示・フィルタ用。ok でも期限超過なら stale。"""
    st = str(v.get("alive_status") or "unknown").strip() or "unknown"
    if st not in ALIVE_STATUSES:
        st = "unknown"
    if st == "ok" and is_overdue(v, kind=kind, today=today):
        return "stale"
    if st in ("unknown", "fail") and is_overdue(v, kind=kind, today=today):
        # 期限超過の未確認は stale 扱い（キューで拾う）
        if days_since_checked(v, today=today) is not None and st == "unknown":
            return "stale"
        if days_since_checked(v, today=today) is None:
            return "stale"
    return st


def is_alive_ok(v: dict[str, Any], *, kind: str, today: date | None = None) -> bool:
    """依頼候補の先頭条件: status=ok かつ期限内。"""
    return effective_alive_status(v, kind=kind, today=today) == "ok"


def ensure_alive_fields(v: dict[str, Any], *, kind: str) -> dict[str, Any]:
    """欠損キーを埋める（in-place）。"""
    v.setdefault("alive_checked_at", "")
    st = str(v.get("alive_status") or "unknown").strip() or "unknown"
    if st not in ALIVE_STATUSES:
        st = "unknown"
    v["alive_status"] = st
    method = str(v.get("alive_method") or "").strip()
    if method and method not in ALIVE_METHODS:
        method = ""
    v["alive_method"] = method
    v.setdefault("alive_note", "")
    if v.get("alive_due_days") in (None, ""):
        v["alive_due_days"] = DEFAULT_DUE_DAYS.get(kind, 180)
    return v


def mark_alive(
    v: dict[str, Any],
    *,
    status: str,
    method: str = "phone",
    note: str = "",
    kind: str = "re",
    checked_at: str | None = None,
) -> dict[str, Any]:
    """電話／手動結果を行に反映。"""
    ensure_alive_fields(v, kind=kind)
    st = (status or "").strip().lower()
    if st not in ALIVE_STATUSES or st == "stale":
        # stale は計算結果。人が付けるのは ok/fail/unknown
        if st != "unknown" and st not in ("ok", "fail"):
            raise ValueError(f"invalid alive_status: {status}")
    if st == "stale":
        st = "unknown"
    meth = (method or "phone").strip().lower()
    if meth not in ALIVE_METHODS or not meth:
        meth = "phone"
    prev_method = str(v.get("alive_method") or "").strip()
    if prev_method == "web" and meth == "phone":
        meth = "both"
    elif prev_method == "phone" and meth == "web":
        meth = "both"
    elif prev_method == "both":
        meth = "both"
    v["alive_status"] = st
    v["alive_method"] = meth
    v["alive_checked_at"] = (checked_at or today_iso())[:10]
    if note:
        prev = str(v.get("alive_note") or "").strip()
        v["alive_note"] = note if not prev else f"{prev} | {note}"
    v["updated_at"] = datetime.now(timezone.utc).isoformat()
    return v


def apply_web_result(
    v: dict[str, Any],
    *,
    web_ok: bool,
    note: str = "",
    kind: str = "re",
) -> bool:
    """Web 自動結果を反映。電話 ok は上書きしない。変更したら True。"""
    ensure_alive_fields(v, kind=kind)
    method = str(v.get("alive_method") or "").strip()
    status = str(v.get("alive_status") or "unknown").strip()
    # 電話で ok 済み → web はメモのみ（status 維持）
    if status == "ok" and method in ("phone", "both") and not is_overdue(v, kind=kind):
        if note:
            prev = str(v.get("alive_note") or "").strip()
            extra = f"web:{note}"
            v["alive_note"] = extra if not prev else f"{prev} | {extra}"
        return bool(note)

    new_status = "ok" if web_ok else "fail"
    # 既に同じ web 結果で期限内ならスキップ
    if (
        status == new_status
        and method in ("web", "both")
        and not is_overdue(v, kind=kind)
    ):
        return False

    if method == "phone":
        new_method = "both"
    else:
        new_method = "web"
    v["alive_status"] = new_status
    v["alive_method"] = new_method
    v["alive_checked_at"] = today_iso()
    if note:
        prev = str(v.get("alive_note") or "").strip()
        extra = f"web:{note}"
        v["alive_note"] = extra if not prev else f"{prev} | {extra}"
    v["updated_at"] = datetime.now(timezone.utc).isoformat()
    return True


def alive_queue_score(v: dict[str, Any], *, kind: str, today: date | None = None) -> tuple:
    """小さいほど優先（期限超過・未確認・fail）。"""
    days = days_since_checked(v, today=today)
    overdue = is_overdue(v, kind=kind, today=today)
    st = str(v.get("alive_status") or "unknown")
    # 優先: overdue > fail > unknown > ok(期限内は通常キュー外)
    bucket = 0 if overdue else 1
    if st == "fail":
        st_rank = 0
    elif st in ("unknown", "stale", ""):
        st_rank = 1
    elif st == "ok":
        st_rank = 3
    else:
        st_rank = 2
    age = days if days is not None else 10_000
    return (bucket, st_rank, -age, str(v.get("id") or ""))


def build_alive_queue(
    vendors: list[dict[str, Any]],
    *,
    kind: str,
    limit: int = 5,
    only_overdue: bool = True,
) -> list[dict[str, Any]]:
    """電話確認キュー。期限切れ（未確認含む）を優先。"""
    today = date.today()
    cand: list[dict[str, Any]] = []
    for v in vendors:
        if not isinstance(v, dict) or not v.get("id"):
            continue
        if str(v.get("status") or "") in ("skip", "invalid"):
            continue
        ensure_alive_fields(v, kind=kind)
        if only_overdue and not is_overdue(v, kind=kind, today=today):
            continue
        # 期限内の ok は電話キュー不要
        if is_alive_ok(v, kind=kind, today=today):
            continue
        cand.append(v)
    cand.sort(key=lambda x: alive_queue_score(x, kind=kind, today=today))
    return cand[: max(0, limit)]


def alive_db_fields(v: dict[str, Any], *, kind: str) -> dict[str, Any]:
    """Supabase upsert 用の alive 列。"""
    ensure_alive_fields(v, kind=kind)
    checked = str(v.get("alive_checked_at") or "").strip()[:10] or None
    return {
        "alive_checked_at": checked,
        "alive_status": str(v.get("alive_status") or "unknown"),
        "alive_method": str(v.get("alive_method") or "") or None,
        "alive_note": (str(v.get("alive_note") or "")[:500] or None),
        "alive_due_days": int(due_days_for(v, kind=kind)),
    }


def pick_check_url(v: dict[str, Any]) -> str:
    for key in ("url", "contact_url"):
        u = str(v.get(key) or "").strip()
        if u.startswith("http://") or u.startswith("https://"):
            return u
    return ""
