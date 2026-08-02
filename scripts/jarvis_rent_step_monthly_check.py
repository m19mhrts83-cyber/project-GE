#!/usr/bin/env python3
"""Grandole 家賃ステップアップ（入居1年 +4,000）月次確認。

使い方:
  python scripts/jarvis_rent_step_monthly_check.py
  python scripts/jarvis_rent_step_monthly_check.py --mark-done
  python scripts/jarvis_rent_step_monthly_check.py --status
  python scripts/jarvis_rent_step_monthly_check.py --build-only

データ:
  - 帳簿家賃: .jarvis_state/property_occupancy.json または Supabase property_units
  - 入居日: 家賃マップ note の「→入居 YY/M」等 + config/rent_step_up.yaml 上書き
  - 入金ヒント: finance_metrics の家賃収入 MoM（号室別ではない弱シグナル）
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

try:
    import yaml
except ImportError:
    yaml = None  # type: ignore

JST = ZoneInfo("Asia/Tokyo")
REPO = Path(__file__).resolve().parents[1]
STATE_DIR = REPO / ".jarvis_state"
STATE_PATH = STATE_DIR / "rent_step_monthly.json"
EXAMPLE_PATH = STATE_DIR / "rent_step_monthly.example.json"
CONFIG_PATH = REPO / "config" / "rent_step_up.yaml"
OCCUPANCY_PATH = STATE_DIR / "property_occupancy.json"
FINANCE_PATH = STATE_DIR / "finance_metrics.json"
PRIVATE_ENV = REPO / ".env.jarvis_private"

MOVE_IN_PATTERNS = [
    re.compile(
        r"(?:→\s*)?入居\s*(\d{2})[/／](\d{1,2})(?:[/／](\d{1,2}))?",
    ),
    re.compile(
        r"→\s*(\d{2})[/／](\d{1,2})(?:[/／](\d{1,2}))?\s*入居",
    ),
    re.compile(
        r"(\d{1,2})[/／](\d{1,2})\s*[〜～ー\-]*\s*入居",
    ),
]
CAMPAIGN_END_RE = re.compile(
    r"(?:＊|\*)?\s*(\d{2})[/／](\d{1,2})\s*まで.*?(?:▲|△|−|-)?\s*4[,，]?000|"
    r"[〜～]\s*(\d{1,2})\s*月まで.*?1年目|"
    r"1年目.*?(\d{1,2})\s*月まで"
)
YEN_RE = re.compile(r"(\d{1,3}(?:,\d{3})+|\d{4,6})\s*円")


def now_jst() -> datetime:
    return datetime.now(JST)


def ym_key(d: date | datetime | None = None) -> str:
    if d is None:
        d = now_jst()
    if isinstance(d, datetime):
        d = d.date()
    return d.strftime("%Y-%m")


def load_dotenv(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.is_file():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.+?)\s*$", line)
        if m and not line.lstrip().startswith("#"):
            out[m.group(1)] = m.group(2).strip().strip("\"'")
    return out


def load_json(path: Path, default: Any = None) -> Any:
    if path.is_file():
        return json.loads(path.read_text(encoding="utf-8"))
    return {} if default is None else default


def save_state(state: dict) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(
        json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def load_config() -> dict[str, Any]:
    if not CONFIG_PATH.is_file() or yaml is None:
        return {
            "defaults": {
                "delta_yen": 4000,
                "upcoming_days": 45,
                "property_ids": ["grandole-i", "grandole-ii"],
            },
            "units": [],
        }
    return yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8")) or {}


def yy_mm_to_date(yy: int, mm: int, dd: int = 1) -> date:
    year = 2000 + yy if yy < 100 else yy
    dd = max(1, min(dd, 28 if mm == 2 else 30 if mm in (4, 6, 9, 11) else 31))
    return date(year, mm, dd)


def parse_move_in(note: str, today: date) -> date | None:
    text = (note or "").replace("\n", " ")
    for pat in MOVE_IN_PATTERNS:
        m = pat.search(text)
        if not m:
            continue
        g = m.groups()
        # patterns with yy/mm[/dd]
        if len(g) >= 2 and g[0] and g[1] and len(g[0]) == 2:
            yy, mm = int(g[0]), int(g[1])
            dd = int(g[2]) if len(g) > 2 and g[2] else 1
            return yy_mm_to_date(yy, mm, dd)
        # mm/dd without year — assume current or previous year
        if len(g) >= 2 and g[0] and g[1] and len(g[0]) <= 2:
            mm, dd = int(g[0]), int(g[1])
            if not (1 <= mm <= 12 and 1 <= dd <= 31):
                continue
            cand = date(today.year, mm, min(dd, 28))
            if cand > today + timedelta(days=60):
                cand = date(today.year - 1, mm, min(dd, 28))
            return cand
    return None


def parse_campaign_end_ym(note: str) -> str | None:
    text = (note or "").replace("\n", " ")
    m = CAMPAIGN_END_RE.search(text)
    if not m:
        return None
    if m.group(1) and m.group(2):
        return f"{2000 + int(m.group(1)):04d}-{int(m.group(2)):02d}"
    month = m.group(3) or m.group(4)
    if month:
        # 年は文脈依存 — 直近の未来月を仮定
        mm = int(month)
        y = now_jst().year
        if date(y, mm, 1) < now_jst().date().replace(day=1):
            # 過ぎていれば当年のその月だった可能性 → 当年のまま（すでに期限）
            pass
        return f"{y:04d}-{mm:02d}"
    return None


def unit_overrides(cfg: dict) -> dict[tuple[str, str], dict]:
    out: dict[tuple[str, str], dict] = {}
    for u in cfg.get("units") or []:
        if not isinstance(u, dict):
            continue
        pid, room = str(u.get("property_id") or ""), str(u.get("room") or "")
        if pid and room:
            out[(pid, room)] = u
    return out


def fetch_units_supabase() -> list[dict[str, Any]]:
    env = load_dotenv(PRIVATE_ENV)
    url = (env.get("JARVIS_SUPABASE_URL") or os.environ.get("JARVIS_SUPABASE_URL") or "").rstrip(
        "/"
    )
    key = env.get("JARVIS_SUPABASE_SERVICE_ROLE_KEY") or os.environ.get(
        "JARVIS_SUPABASE_SERVICE_ROLE_KEY"
    )
    if not url or not key:
        return []
    q = (
        f"{url}/rest/v1/property_units"
        "?or=(property_id.eq.grandole-i,property_id.eq.grandole-ii)"
        "&select=property_id,property_name,room,status,rent,note,payload"
        "&order=property_id,room"
    )
    req = Request(q, headers={"apikey": key, "Authorization": f"Bearer {key}"})
    with urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())


def load_units(property_ids: list[str]) -> list[dict[str, Any]]:
    rows = fetch_units_supabase()
    if not rows and OCCUPANCY_PATH.is_file():
        data = load_json(OCCUPANCY_PATH)
        rows = data.get("units") or []
    out = []
    for r in rows:
        if str(r.get("property_id") or "") in property_ids:
            out.append(r)
    return out


def zaim_rent_hint() -> dict[str, Any] | None:
    data = load_json(FINANCE_PATH)
    metrics = data.get("metrics") if isinstance(data, dict) else None
    if not isinstance(metrics, list):
        # flat list of rows
        rows = data if isinstance(data, list) else data.get("rows") if isinstance(data, dict) else []
        if not isinstance(rows, list):
            return None
        metrics = rows
    by_ym: dict[str, float] = {}
    for m in metrics:
        if not isinstance(m, dict):
            continue
        if m.get("metric") != "rent_income":
            continue
        ym = str(m.get("recorded_at") or m.get("ym") or "")[:7]
        if not re.match(r"^\d{4}-\d{2}$", ym):
            continue
        by_ym[ym] = by_ym.get(ym, 0) + float(m.get("value") or 0)
    if len(by_ym) < 2:
        return None
    yms = sorted(by_ym.keys())
    cur, prev = yms[-1], yms[-2]
    delta = by_ym[cur] - by_ym[prev]
    return {
        "current_ym": cur,
        "previous_ym": prev,
        "current_yen": round(by_ym[cur]),
        "previous_yen": round(by_ym[prev]),
        "delta_yen": round(delta),
        "note": "号室別ではない。ポートフォリオ家賃収入の前月差（弱シグナル）",
    }


def short_label(pid: str, room: str, name: str | None) -> str:
    if pid == "grandole-i":
        return f"I-{room}"
    if pid == "grandole-ii":
        return f"II-{room}"
    return f"{name or pid}-{room}"


def evaluate_unit(
    row: dict[str, Any],
    ov: dict[str, Any],
    delta_yen: int,
    upcoming_days: int,
    today: date,
    prev_snap: dict[str, Any],
) -> dict[str, Any]:
    pid = str(row.get("property_id") or "")
    room = str(row.get("room") or "")
    uid = f"{pid}-{room}"
    note = str(row.get("note") or "")
    rent = row.get("rent")
    try:
        rent_n = int(rent) if rent is not None else None
    except (TypeError, ValueError):
        rent_n = None
    status = str(row.get("status") or "")
    name = str(row.get("property_name") or "")

    move_in: date | None = None
    if ov.get("move_in"):
        try:
            move_in = date.fromisoformat(str(ov["move_in"])[:10])
        except ValueError:
            move_in = None
    if move_in is None:
        move_in = parse_move_in(note, today)

    campaign_end_ym = ov.get("campaign_end_ym") or parse_campaign_end_ym(note)
    year1 = ov.get("year1_rent")
    year2 = ov.get("year2_rent")
    if year1 is None and rent_n is not None:
        # 帳簿がすでに2年目なら year1 = rent - delta の仮説は危険なので、メモの1年目額を探す
        m = re.search(r"1年目\s*(\d{1,3}(?:,\d{3})+|\d+)\s*円", note)
        if m:
            year1 = int(m.group(1).replace(",", ""))
    if year1 is None and rent_n is not None:
        year1 = rent_n  # 暫定: 現状帳簿を1年目扱い（入居1年未満のとき）
    if year2 is None and year1 is not None:
        year2 = int(year1) + delta_yen

    anniversary: date | None = None
    if move_in:
        try:
            anniversary = move_in.replace(year=move_in.year + 1)
        except ValueError:
            anniversary = move_in + timedelta(days=365)
    elif campaign_end_ym and re.match(r"^\d{4}-\d{2}$", str(campaign_end_ym)):
        y, m = map(int, str(campaign_end_ym).split("-"))
        # キャンペーン終了月の翌月1日を切替とみなす
        if m == 12:
            anniversary = date(y + 1, 1, 1)
        else:
            anniversary = date(y, m + 1, 1)

    expected: int | None = None
    phase = "unknown"
    if anniversary and year1 is not None and year2 is not None:
        if today < anniversary:
            expected = int(year1)
            phase = "year1"
            days_left = (anniversary - today).days
            if days_left <= upcoming_days:
                phase = "upcoming"
        else:
            expected = int(year2)
            phase = "year2"

    gap = None
    if expected is not None and rent_n is not None:
        gap = rent_n - expected

    prev_rent = prev_snap.get(uid)
    changed = (
        prev_rent is not None
        and rent_n is not None
        and int(prev_rent) != rent_n
    )

    flag = "ok"
    reason = ""
    if status != "occupied":
        flag = "skip"
        reason = "空室"
    elif phase == "unknown" or expected is None:
        flag = "unknown"
        reason = "入居日または期待家賃が不明"
    elif phase == "upcoming":
        flag = "upcoming"
        y2s = f"{int(year2):,}円" if year2 is not None else "—"
        reason = f"あと{(anniversary - today).days}日で2年目（期待 {y2s}）"
    elif phase == "year2" and rent_n is not None and year2 is not None and rent_n < int(year2) - 500:
        flag = "overdue"
        reason = f"2年目相当だが帳簿 {rent_n:,}円 < 期待 {int(year2):,}円（+{delta_yen}未反映の疑い）"
    elif changed:
        flag = "changed"
        reason = f"帳簿家賃が変動 {int(prev_rent):,} → {rent_n:,}円"
    elif phase == "year2" and rent_n is not None and year2 is not None and abs(rent_n - int(year2)) <= 500:
        flag = "ok"
        reason = "2年目帯で一致"
    elif phase == "year1":
        flag = "ok"
        reason = "1年目帯"

    if changed and flag == "ok":
        flag = "changed"
        reason = f"帳簿家賃が変動 {int(prev_rent):,} → {rent_n:,}円"

    return {
        "id": uid,
        "label": short_label(pid, room, name),
        "property_id": pid,
        "property_name": name,
        "room": room,
        "status": status,
        "book_rent": rent_n,
        "prev_book_rent": int(prev_rent) if prev_rent is not None else None,
        "year1_rent": int(year1) if year1 is not None else None,
        "year2_rent": int(year2) if year2 is not None else None,
        "expected_rent": expected,
        "gap_yen": gap,
        "move_in": move_in.isoformat() if move_in else None,
        "anniversary": anniversary.isoformat() if anniversary else None,
        "campaign_end_ym": campaign_end_ym,
        "phase": phase,
        "flag": flag,
        "reason": reason,
        "note_snip": note.replace("\n", " ")[:80],
    }


def build_summary(units: list[dict[str, Any]], zaim: dict | None) -> dict[str, Any]:
    overdue = [u for u in units if u["flag"] == "overdue"]
    upcoming = [u for u in units if u["flag"] == "upcoming"]
    changed = [u for u in units if u["flag"] == "changed"]
    unknown = [u for u in units if u["flag"] == "unknown"]
    ok = [u for u in units if u["flag"] == "ok"]
    actionable = bool(overdue or changed or upcoming)
    return {
        "overdue_count": len(overdue),
        "upcoming_count": len(upcoming),
        "changed_count": len(changed),
        "unknown_count": len(unknown),
        "ok_count": len(ok),
        "actionable": actionable,
        "overdue": [{"id": u["id"], "label": u["label"], "reason": u["reason"]} for u in overdue],
        "upcoming": [{"id": u["id"], "label": u["label"], "reason": u["reason"]} for u in upcoming],
        "changed": [
            {
                "id": u["id"],
                "label": u["label"],
                "from": u["prev_book_rent"],
                "to": u["book_rent"],
                "reason": u["reason"],
            }
            for u in changed
        ],
        "zaim_hint": zaim,
    }


def run_build(*, mark_done: bool) -> dict[str, Any]:
    cfg = load_config()
    defaults = cfg.get("defaults") or {}
    delta = int(defaults.get("delta_yen") or 4000)
    upcoming_days = int(defaults.get("upcoming_days") or 45)
    property_ids = list(defaults.get("property_ids") or ["grandole-i", "grandole-ii"])
    overrides = unit_overrides(cfg)

    state = load_json(STATE_PATH)
    if not state and EXAMPLE_PATH.is_file():
        state = load_json(EXAMPLE_PATH)
    if not isinstance(state, dict):
        state = {}

    today = now_jst().date()
    target = ym_key(today)
    prev_snap = dict(state.get("prev_rent_snapshot") or {})

    rows = load_units(property_ids)
    units = [
        evaluate_unit(
            r,
            overrides.get((str(r.get("property_id")), str(r.get("room"))), {}),
            delta,
            upcoming_days,
            today,
            prev_snap,
        )
        for r in rows
    ]
    zaim = zaim_rent_hint()
    summary = build_summary(units, zaim)

    # history of changes
    hist = [h for h in (state.get("change_history") or []) if isinstance(h, dict)]
    for u in units:
        if u["flag"] == "changed":
            entry = {
                "at": now_jst().isoformat(timespec="seconds"),
                "target_month": target,
                "id": u["id"],
                "label": u["label"],
                "from": u["prev_book_rent"],
                "to": u["book_rent"],
            }
            if not any(
                h.get("id") == entry["id"]
                and h.get("to") == entry["to"]
                and h.get("target_month") == target
                for h in hist
            ):
                hist.insert(0, entry)
    hist = hist[:40]

    new_snap = {
        u["id"]: u["book_rent"]
        for u in units
        if u.get("book_rent") is not None
    }

    result = {
        "at": now_jst().isoformat(timespec="seconds"),
        "ok": not summary["overdue_count"],
        "target_month": target,
        "summary": summary,
        "units": units,
        "zaim_hint": zaim,
        "delta_yen": delta,
        "note": "帳簿=property_units。入金は号室別未連携のため Zaim 家賃収入を参考表示。",
        "grant_rule": "Grandole は入居から1年で家賃 +4,000円。月次で帳簿と入居日起算を確認。",
    }

    # show_banner 用: 未確認のアクションがあれば target_month を立てる
    state["last_result"] = result
    if mark_done:
        state["last_check"] = target
    else:
        state["last_check"] = target  # 結果更新は毎回。確認(ack)とは独立
    state["change_history"] = hist
    state["prev_rent_snapshot"] = new_snap
    # dashboard_ack_target_month は触らない
    if "disabled" not in state:
        state["disabled"] = False
    save_state(state)
    return result


def print_block(result: dict[str, Any]) -> None:
    s = result.get("summary") or {}
    print("---")
    print(f"📎 Grandole家賃ステップ — {result.get('target_month')}")
    print(
        f"- 要対応: 未反映 {s.get('overdue_count', 0)} · 変動 {s.get('changed_count', 0)} · まもなく {s.get('upcoming_count', 0)} · OK {s.get('ok_count', 0)}"
    )
    for u in s.get("overdue") or []:
        print(f"  ⚠ {u.get('label')}: {u.get('reason')}")
    for u in s.get("changed") or []:
        print(f"  ↔ {u.get('label')}: {u.get('reason')}")
    for u in s.get("upcoming") or []:
        print(f"  … {u.get('label')}: {u.get('reason')}")
    zh = result.get("zaim_hint")
    if zh:
        print(
            f"- Zaim家賃収入ヒント: {zh.get('previous_ym')}→{zh.get('current_ym')} "
            f"{zh.get('delta_yen'):+,}円"
        )
    print(f"- 判定: {'✅ 問題なし' if result.get('ok') else '⚠️ 要フォロー'}")
    print("---")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mark-done", action="store_true")
    ap.add_argument("--build-only", action="store_true")
    ap.add_argument("--status", action="store_true")
    args = ap.parse_args()

    if args.status:
        st = load_json(STATE_PATH)
        print(json.dumps(st.get("last_result") or st, ensure_ascii=False, indent=2))
        return 0

    result = run_build(mark_done=args.mark_done or args.build_only)
    print_block(result)
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
