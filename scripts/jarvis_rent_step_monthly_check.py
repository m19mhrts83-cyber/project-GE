#!/usr/bin/env python3
"""Grandole 家賃ステップアップ（入居1年 +4,000）月次確認。

使い方:
  python scripts/jarvis_rent_step_monthly_check.py
  python scripts/jarvis_rent_step_monthly_check.py --mark-done
  python scripts/jarvis_rent_step_monthly_check.py --status
  python scripts/jarvis_rent_step_monthly_check.py --build-only
  python scripts/jarvis_rent_step_monthly_check.py --no-follow-drafts

データ:
  - 帳簿家賃: .jarvis_state/property_occupancy.json または Supabase property_units
  - 入居日: 家賃マップ note の「→入居 YY/M」等 + config/rent_step_up.yaml 上書き
  - 入金: scripts/jarvis_rent_deposit_ingest.py（LEAF/ミニテック/Tcell PDF）
  - 合算フォールバック: HP=MUFG、Tcell明細なし=物件口座（PayPay/滋賀）＋メモ
  - 入金未確認フォロー下書き: jarvis_rent_deposit_follow_drafts.py
    （4.送信下書き_家賃入金フォロー.txt。送る前に --promote）
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
DEPOSITS_PATH = STATE_DIR / "rent_deposits.json"
BASELINE_PATH = STATE_DIR / "rent_vacancy_baseline.json"
PROPERTY_INFO_PATH = REPO / "config" / "property_info.yaml"
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


def resolve_manager(property_id: str, room: str, note: str = "") -> str | None:
    """config/property_info.yaml から号室の管理会社を解決。"""
    if yaml is None or not PROPERTY_INFO_PATH.is_file():
        return None
    info = yaml.safe_load(PROPERTY_INFO_PATH.read_text(encoding="utf-8")) or {}
    props = info.get("properties") or {}
    p = props.get(property_id) or {}
    rooms = p.get("rooms") or {}
    if isinstance(rooms.get(room), dict) and rooms[room].get("manager"):
        return str(rooms[room]["manager"])
    m = re.search(r"(LEAF|Tcell|ミニテック|ホームプランナー)", note or "", re.I)
    if m:
        s = m.group(1)
        if s.lower() == "leaf":
            return "LEAF"
        if s.lower() == "tcell":
            return "Tcell"
        return s
    if p.get("default_manager"):
        return str(p["default_manager"])
    mgrs = p.get("managers") or []
    if len(mgrs) == 1:
        return str(mgrs[0])
    return None


def load_deposits() -> dict[str, Any]:
    return load_json(DEPOSITS_PATH, {})


def ensure_deposits(ym: str | None = None) -> dict[str, Any]:
    try:
        from jarvis_rent_deposit_ingest import run_ingest  # type: ignore
    except ImportError:
        import importlib.util

        path = REPO / "scripts" / "jarvis_rent_deposit_ingest.py"
        spec = importlib.util.spec_from_file_location("jarvis_rent_deposit_ingest", path)
        if spec is None or spec.loader is None:
            return load_deposits()
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod.run_ingest(ym)
    return run_ingest(ym)


def room_deposit_index(deposits: dict[str, Any], ym: str) -> dict[tuple[str, str], dict]:
    """(property_id, room) → best entry for ym (prefer any source)."""
    out: dict[tuple[str, str], dict] = {}
    for e in deposits.get("room_entries") or []:
        if e.get("ym") != ym:
            continue
        pid, room = str(e.get("property_id") or ""), str(e.get("room") or "")
        if not pid or not room:
            continue
        key = (pid, room)
        # prefer later sources overwritten; leaf/minitech/tcell all fine
        out[key] = e
    return out


def bank_agg_map(deposits: dict[str, Any], ym: str) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for b in deposits.get("bank_aggregates") or []:
        if b.get("ym") == ym and b.get("bank_id"):
            out[str(b["bank_id"])] = b
    return out


def zaim_rent_hint() -> dict[str, Any] | None:
    """廃止: 号室判断には使わない（互換で None）。"""
    return None


def short_label(pid: str, room: str, name: str | None) -> str:
    if pid == "grandole-i":
        return f"I-{room}"
    if pid == "grandole-ii":
        return f"II-{room}"
    return f"{name or pid}-{room}"


def load_vacancy_baseline() -> dict[tuple[str, str], dict]:
    """空室対策メール正本。無ければ生成を試みる。"""
    try:
        from jarvis_rent_vacancy_mail_baseline import (  # type: ignore
            baseline_index,
            build_baseline,
            resolve_mail_dir,
        )
        from jarvis_rent_vacancy_mail_baseline import OUT_PATH as BL_OUT  # type: ignore
    except ImportError:
        path = REPO / "scripts" / "jarvis_rent_vacancy_mail_baseline.py"
        if not path.is_file():
            data = load_json(BASELINE_PATH, {})
            out: dict[tuple[str, str], dict] = {}
            for u in data.get("units") or []:
                out[(str(u.get("property_id")), str(u.get("room")))] = u
            return out
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "jarvis_rent_vacancy_mail_baseline", path
        )
        if spec is None or spec.loader is None:
            return {}
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        baseline_index = mod.baseline_index
        build_baseline = mod.build_baseline
        resolve_mail_dir = mod.resolve_mail_dir
        BL_OUT = mod.OUT_PATH

    if not BASELINE_PATH.is_file():
        mail_dir = resolve_mail_dir()
        if mail_dir.is_dir():
            data = build_baseline(mail_dir)
            STATE_DIR.mkdir(parents=True, exist_ok=True)
            BASELINE_PATH.write_text(
                json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
    return baseline_index()


def evaluate_unit(
    row: dict[str, Any],
    ov: dict[str, Any],
    delta_yen: int,
    upcoming_days: int,
    today: date,
    prev_snap: dict[str, Any],
    *,
    baseline: dict[tuple[str, str], dict] | None = None,
    overdue_grace_days: int = 30,
    follow_draft_grace_days: int = 60,
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
    bl = (baseline or {}).get((pid, room)) or {}

    move_in: date | None = None
    if ov.get("move_in"):
        try:
            move_in = date.fromisoformat(str(ov["move_in"])[:10])
        except ValueError:
            move_in = None
    if move_in is None and bl.get("move_in"):
        try:
            move_in = date.fromisoformat(str(bl["move_in"])[:10])
        except ValueError:
            move_in = None
    if move_in is None:
        move_in = parse_move_in(note, today)

    campaign_end_ym = ov.get("campaign_end_ym") or parse_campaign_end_ym(note)

    # 想定家賃優先: vacancy_mail → yaml → note
    year1 = bl.get("year1_rent") if bl.get("year1_rent") is not None else None
    year2 = bl.get("year2_rent") if bl.get("year2_rent") is not None else None
    rent_source = "vacancy_mail" if year1 is not None else None
    if ov.get("year1_rent") is not None:
        year1 = ov.get("year1_rent")
        rent_source = "yaml_override"
    if ov.get("year2_rent") is not None:
        year2 = ov.get("year2_rent")
        rent_source = rent_source or "yaml_override"
    if year1 is None and rent_n is not None:
        m = re.search(r"1年目\s*(\d{1,3}(?:,\d{3})+|\d+)\s*円", note)
        if m:
            year1 = int(m.group(1).replace(",", ""))
            rent_source = "occupancy_note"
    if year1 is None and rent_n is not None:
        year1 = rent_n
        rent_source = rent_source or "book_rent"
    if year2 is None and year1 is not None:
        year2 = int(year1) + delta_yen

    # 入居日ズバリ +1年
    anniversary: date | None = None
    if move_in:
        try:
            anniversary = move_in.replace(year=move_in.year + 1)
        except ValueError:
            anniversary = move_in + timedelta(days=365)
    elif campaign_end_ym and re.match(r"^\d{4}-\d{2}$", str(campaign_end_ym)):
        y, m = map(int, str(campaign_end_ym).split("-"))
        if m == 12:
            anniversary = date(y + 1, 1, 1)
        else:
            anniversary = date(y, m + 1, 1)

    expected: int | None = None
    phase = "unknown"
    days_after = None
    if anniversary and year1 is not None and year2 is not None:
        if today < anniversary:
            expected = int(year1)
            phase = "year1"
            if (anniversary - today).days <= upcoming_days:
                phase = "upcoming"
        else:
            days_after = (today - anniversary).days
            if days_after < overdue_grace_days:
                # 様子見期間: 期待は year2 だが未反映でも overdue にしない
                expected = int(year2)
                phase = "grace"
            else:
                expected = int(year2)
                phase = "year2"

    gap = None
    if expected is not None and rent_n is not None:
        gap = rent_n - expected

    prev_rent = prev_snap.get(uid)
    changed = (
        prev_rent is not None and rent_n is not None and int(prev_rent) != rent_n
    )

    flag = "ok"
    reason = ""
    step_follow_ready = False
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
    elif phase == "grace":
        flag = "grace"
        reason = (
            f"1年経過後の様子見（+{days_after}日/"
            f"猶予{overdue_grace_days}日）。期待 {int(year2):,}円"
            if year2 is not None and days_after is not None
            else "1年経過後の様子見"
        )
    elif (
        phase == "year2"
        and rent_n is not None
        and year2 is not None
        and rent_n < int(year2) - 500
    ):
        flag = "overdue"
        reason = (
            f"2年目相当（記念日+{overdue_grace_days}日超）だが帳簿 "
            f"{rent_n:,}円 < 期待 {int(year2):,}円"
            f"（+{delta_yen}未反映の疑い）"
        )
        if days_after is not None and days_after >= follow_draft_grace_days:
            step_follow_ready = True
            reason += f" · フォロー候補（+{follow_draft_grace_days}日超）"
    elif changed:
        flag = "changed"
        reason = f"帳簿家賃が変動 {int(prev_rent):,} → {rent_n:,}円"
    elif (
        phase == "year2"
        and rent_n is not None
        and year2 is not None
        and abs(rent_n - int(year2)) <= 500
    ):
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
        "days_after_anniversary": days_after,
        "rent_source": rent_source,
        "baseline_source": bl.get("source_file"),
        "step_follow_ready": step_follow_ready,
        "flag": flag,
        "reason": reason,
        "note_snip": note.replace("\n", " ")[:80],
    }


def attach_deposits(
    units: list[dict[str, Any]],
    cfg: dict[str, Any],
    deposits: dict[str, Any],
    target_ym: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """号室に observed_deposit を付与し、合算ブロック（HP/Tcellフォールバック）を返す。"""
    defaults = cfg.get("defaults") or {}
    mismatch_thr = int(defaults.get("deposit_mismatch_yen") or 500)
    gap_alert = int(defaults.get("aggregate_gap_alert_yen") or 30000)
    accounts = cfg.get("deposit_accounts") or {}
    memos = cfg.get("aggregate_memos") or {}
    room_ix = room_deposit_index(deposits, target_ym)
    y, m = map(int, target_ym.split("-"))
    prev_ym = f"{y - 1}-12" if m == 1 else f"{y:04d}-{m - 1:02d}"
    y2, m2 = (y - 1, 12) if m == 1 else (y, m - 1)
    prev2_ym = f"{y2 - 1}-12" if m2 == 1 else f"{y2:04d}-{m2 - 1:02d}"
    room_ix_prev = room_deposit_index(deposits, prev_ym)
    room_ix_prev2 = room_deposit_index(deposits, prev2_ym)
    banks = bank_agg_map(deposits, target_ym)
    banks_prev = bank_agg_map(deposits, prev_ym)

    def pick_bank(bank_id: str) -> dict | None:
        cur = banks.get(bank_id)
        prev = banks_prev.get(bank_id)
        # 当月がほぼ空（利息のみ等）なら前月の家賃カテゴリを使う
        if cur and int(cur.get("amount_yen") or 0) >= 10000:
            return cur
        if prev and int(prev.get("amount_yen") or 0) >= 10000:
            return prev
        return cur or prev

    for u in units:
        pid, room = u["property_id"], u["room"]
        mgr = resolve_manager(pid, room, u.get("note_snip") or "")
        u["manager"] = mgr
        dep = (
            room_ix.get((pid, room))
            or room_ix_prev.get((pid, room))
            or room_ix_prev2.get((pid, room))
        )
        u["observed_deposit"] = None
        u["deposit_source"] = None
        u["deposit_ym"] = None
        u["deposit_gap_yen"] = None
        u["deposit_flag"] = None
        if dep and dep.get("rent_yen") is not None:
            obs = int(dep["rent_yen"])
            u["observed_deposit"] = obs
            u["deposit_source"] = dep.get("source")
            u["deposit_ym"] = dep.get("ym")
            # 明細対象月時点の期待家賃（キャンペーン中は year1）
            exp = u.get("book_rent")
            ann = u.get("anniversary")
            y1, y2r = u.get("year1_rent"), u.get("year2_rent")
            if ann and u.get("deposit_ym") and y1 is not None:
                try:
                    dep_month = date.fromisoformat(str(u["deposit_ym"]) + "-01")
                    ann_d = date.fromisoformat(str(ann)[:10])
                    if dep_month < ann_d.replace(day=1):
                        exp = int(y1)
                    elif y2r is not None:
                        exp = int(y2r)
                except ValueError:
                    pass
            if exp is not None:
                gap = obs - int(exp)
                u["deposit_gap_yen"] = gap
                if abs(gap) > mismatch_thr:
                    u["deposit_flag"] = "deposit_mismatch"
                    if u["flag"] in ("ok", "upcoming", "unknown"):
                        u["flag"] = "deposit_mismatch"
                        u["reason"] = (
                            f"入金家賃 {obs:,} ≠ 期待 {int(exp):,}（差 {gap:+,}）"
                            f" [{u['deposit_source']} {u['deposit_ym']}]"
                        )
                else:
                    u["deposit_flag"] = "deposit_ok"
            continue

        if mgr in ("ホームプランナー",):
            # 紙明細 → 口座合算＋メモ（号室PDFなし）
            u["deposit_flag"] = "aggregate"
        elif mgr == "Tcell":
            # LINE明細なし → HPと同型（物件口座合算＋メモ）
            u["deposit_flag"] = "aggregate"
        elif mgr == "LEAF":
            # くらさぽPDFなし → 京都合算（PayPay にも着金するため号室正本は PDF）
            u["deposit_flag"] = "aggregate"
        elif mgr == "ミニテック":
            u["deposit_flag"] = "deposit_missing"

    aggregates: list[dict[str, Any]] = []

    def add_aggregate(
        group: str,
        property_id: str,
        bank_id: str,
        unit_subset: list[dict[str, Any]],
        title: str,
    ) -> None:
        book_sum = sum(
            int(u["book_rent"]) for u in unit_subset if u.get("book_rent") is not None
        )
        bank = pick_bank(bank_id)
        observed = int(bank["amount_yen"]) if bank else None
        bank_ym = bank.get("ym") if bank else None
        gap = (observed - book_sum) if observed is not None else None
        memo_key = f"{group}:{property_id}:{target_ym}"
        memo = memos.get(memo_key) or memos.get(f"{group}:{target_ym}")
        needs_memo = (
            observed is not None
            and gap is not None
            and abs(gap) >= gap_alert
            and not memo
        )
        missing_bank = observed is None
        acct = accounts.get(property_id) or {}
        if group.startswith("leaf"):
            acct = accounts.get("leaf_legacy") or acct
        aggregates.append(
            {
                "group": group,
                "property_id": property_id,
                "title": title,
                "bank_id": bank_id,
                "bank_label": acct.get("zaim_match") or bank_id,
                "bank_note": acct.get("note") or "",
                "book_rent_sum": book_sum,
                "observed_yen": observed,
                "observed_ym": bank_ym,
                "gap_yen": gap,
                "memo": memo,
                "memo_key": memo_key,
                "needs_memo": needs_memo,
                "missing_bank": missing_bank,
                "rooms": [u["label"] for u in unit_subset],
                "flag": (
                    "needs_memo"
                    if needs_memo
                    else (
                        "missing_bank"
                        if missing_bank
                        else (
                            "ok"
                            if memo
                            or (gap is not None and abs(gap) < gap_alert)
                            else "info"
                        )
                    )
                ),
            }
        )

    # HP: grandole-ii 全号室
    hp_units = [u for u in units if u.get("manager") == "ホームプランナー" and u.get("status") == "occupied"]
    if hp_units:
        add_aggregate(
            "hp",
            "grandole-ii",
            "mufg",
            hp_units,
            "ホームプランナー（紙明細）→ MUFG 合算",
        )

    # Tcell: PDF が無い号室を物件ごとに合算
    for prop, bank_id, title in (
        ("grandole-i", "paypay", "Tcell（明細なし）→ PayPay 合算"),
        ("caramel", "shiga", "Tcell キャラメル（明細なし）→ 滋賀銀行 合算"),
    ):
        subset = [
            u
            for u in units
            if u.get("property_id") == prop
            and u.get("manager") == "Tcell"
            and u.get("status") == "occupied"
            and u.get("observed_deposit") is None
        ]
        if subset:
            add_aggregate("tcell", prop, bank_id, subset, title)

    # LEAF 現行・京都（参考）。号室PDFが無い LEAF 号室があるとき
    leaf_missing = [
        u
        for u in units
        if u.get("manager") == "LEAF"
        and u.get("status") == "occupied"
        and u.get("observed_deposit") is None
    ]
    if leaf_missing:
        add_aggregate(
            "leaf",
            "grandole-i",
            "kyoto",
            leaf_missing,
            "LEAF（明細なし）→ 京都銀行合算（PayPay にも着金。号室はくらさぽPDF）",
        )

    return units, aggregates


def build_summary(
    units: list[dict[str, Any]],
    aggregates: list[dict[str, Any]],
) -> dict[str, Any]:
    overdue = [u for u in units if u["flag"] == "overdue"]
    upcoming = [u for u in units if u["flag"] == "upcoming"]
    grace = [u for u in units if u["flag"] == "grace"]
    changed = [u for u in units if u["flag"] == "changed"]
    deposit_mismatch = [u for u in units if u["flag"] == "deposit_mismatch"]
    deposit_missing = [
        u
        for u in units
        if u.get("deposit_flag") == "deposit_missing" and u.get("observed_deposit") is None
        and u.get("manager") in ("LEAF", "ミニテック")
        and u.get("status") == "occupied"
    ]
    unknown = [u for u in units if u["flag"] == "unknown"]
    ok = [u for u in units if u["flag"] == "ok"]
    agg_need = [a for a in aggregates if a.get("flag") in ("needs_memo", "missing_bank")]
    step_follow = [u for u in units if u.get("step_follow_ready")]
    # 様子見中の grace はバナー注意には含めるが即アクションではない
    actionable = bool(
        overdue or changed or deposit_mismatch or deposit_missing or agg_need or step_follow
    )
    return {
        "overdue_count": len(overdue),
        "upcoming_count": len(upcoming),
        "grace_count": len(grace),
        "changed_count": len(changed),
        "deposit_mismatch_count": len(deposit_mismatch),
        "deposit_missing_count": len(deposit_missing),
        "aggregate_need_count": len(agg_need),
        "step_follow_ready_count": len(step_follow),
        "unknown_count": len(unknown),
        "ok_count": len(ok),
        "actionable": actionable,
        "overdue": [{"id": u["id"], "label": u["label"], "reason": u["reason"]} for u in overdue],
        "upcoming": [{"id": u["id"], "label": u["label"], "reason": u["reason"]} for u in upcoming],
        "grace": [{"id": u["id"], "label": u["label"], "reason": u["reason"]} for u in grace],
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
        "deposit_mismatch": [
            {
                "id": u["id"],
                "label": u["label"],
                "reason": u["reason"],
                "observed": u.get("observed_deposit"),
            }
            for u in deposit_mismatch
        ],
        "deposit_missing": [
            {"id": u["id"], "label": u["label"], "manager": u.get("manager")}
            for u in deposit_missing
        ],
        "aggregates_need": [
            {
                "group": a["group"],
                "title": a["title"],
                "gap_yen": a.get("gap_yen"),
                "memo_key": a.get("memo_key"),
                "flag": a.get("flag"),
            }
            for a in agg_need
        ],
        "step_follow_ready": [
            {"id": u["id"], "label": u["label"], "reason": u["reason"]}
            for u in step_follow
        ],
    }


def run_follow_drafts(result: dict[str, Any], *, dry_run: bool = False) -> dict[str, Any] | None:
    """想定入金未確認のパートナー下書きを生成。失敗しても本処理は続行。"""
    try:
        from jarvis_rent_deposit_follow_drafts import (  # type: ignore
            print_block as print_follow_block,
            run_from_result,
        )
    except ImportError:
        path = REPO / "scripts" / "jarvis_rent_deposit_follow_drafts.py"
        if not path.is_file():
            return None
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "jarvis_rent_deposit_follow_drafts", path
        )
        if spec is None or spec.loader is None:
            return None
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        run_from_result = mod.run_from_result
        print_follow_block = mod.print_block

    out = run_from_result(result, dry_run=dry_run, write_files=not dry_run)
    print_follow_block(out)
    return out


def run_build(*, mark_done: bool, write_follow_drafts: bool = True) -> dict[str, Any]:
    cfg = load_config()
    defaults = cfg.get("defaults") or {}
    delta = int(defaults.get("delta_yen") or 4000)
    upcoming_days = int(defaults.get("upcoming_days") or 45)
    overdue_grace_days = int(defaults.get("overdue_grace_days") or 30)
    follow_draft_grace_days = int(defaults.get("follow_draft_grace_days") or 60)
    deposit_follow_grace_months = int(defaults.get("deposit_follow_grace_months") or 1)
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

    # 空室対策メール正本
    try:
        baseline = load_vacancy_baseline()
    except Exception as e:
        print(f"# vacancy baseline failed: {e}", file=sys.stderr)
        baseline = {}

    # 入金取り込み（失敗しても帳簿判定は続行）
    try:
        deposits = ensure_deposits(None)
    except Exception as e:
        print(f"# deposit ingest failed: {e}", file=sys.stderr)
        deposits = load_deposits()

    rows = load_units(property_ids)
    units = [
        evaluate_unit(
            r,
            overrides.get((str(r.get("property_id")), str(r.get("room"))), {}),
            delta,
            upcoming_days,
            today,
            prev_snap,
            baseline=baseline,
            overdue_grace_days=overdue_grace_days,
            follow_draft_grace_days=follow_draft_grace_days,
        )
        for r in rows
    ]
    units, aggregates = attach_deposits(units, cfg, deposits, target)
    summary = build_summary(units, aggregates)

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
        "ok": not (
            summary["overdue_count"]
            or summary.get("deposit_mismatch_count")
            or summary.get("deposit_missing_count")
            or summary.get("aggregate_need_count")
        ),
        "target_month": target,
        "summary": summary,
        "units": units,
        "aggregates": aggregates,
        "delta_yen": delta,
        "overdue_grace_days": overdue_grace_days,
        "follow_draft_grace_days": follow_draft_grace_days,
        "deposit_follow_grace_months": deposit_follow_grace_months,
        "note": (
            "想定家賃の正本は空室対策メール（入居から1年間キャンペーン）。"
            "1年後は入居日ズバリ。未反映アラートは記念日+30日以降。"
            "入金フォロー下書きは様子見（送金月+1ヶ月）後。"
        ),
        "grant_rule": (
            "Grandole は入居から1年で家賃 +4,000円（空室対策メール準拠・入居日ズバリ）。"
            " 口座: I=PayPay主 / II=MUFG / キャラメル=滋賀 / LEAF=京都＋PayPay併用。"
        ),
    }

    follow_out = None
    if write_follow_drafts:
        try:
            follow_out = run_follow_drafts(result, dry_run=False)
        except Exception as e:
            print(f"# follow drafts failed: {e}", file=sys.stderr)

    if follow_out:
        result["follow_drafts"] = {
            "follow_count": follow_out.get("follow_count"),
            "draft_count": follow_out.get("draft_count"),
            "watch_count": follow_out.get("watch_count"),
            "drafts": [
                {
                    "manager": d.get("manager"),
                    "channel": d.get("channel"),
                    "subject": d.get("subject"),
                    "item_count": d.get("item_count"),
                    "draft_path": d.get("draft_path"),
                    "send_path": d.get("send_path"),
                    "promote_hint": d.get("promote_hint"),
                    "preview": d.get("preview"),
                    "status": d.get("status"),
                    "items": [
                        {
                            "label": i.get("label"),
                            "kind": i.get("kind"),
                            "reason": i.get("reason"),
                            "gap_yen": i.get("gap_yen"),
                            "watch": i.get("watch"),
                        }
                        for i in (d.get("items") or [])
                    ],
                }
                for d in (follow_out.get("drafts") or [])
            ],
            "watching": follow_out.get("watching") or [],
        }
        summary["follow_count"] = follow_out.get("follow_count") or 0
        summary["follow_draft_count"] = follow_out.get("draft_count") or 0
        summary["follow_watch_count"] = follow_out.get("watch_count") or 0
        if summary.get("follow_draft_count"):
            summary["actionable"] = True
            result["ok"] = False

    state["last_result"] = result
    state["last_check"] = target
    state["change_history"] = hist
    state["prev_rent_snapshot"] = new_snap
    if follow_out:
        state["follow_drafts"] = follow_out
    if "disabled" not in state:
        state["disabled"] = False
    save_state(state)
    return result


def print_block(result: dict[str, Any]) -> None:
    s = result.get("summary") or {}
    print("---")
    print(f"📎 Grandole家賃ステップ — {result.get('target_month')}")
    print(
        f"- 要対応: 未反映 {s.get('overdue_count', 0)} · 様子見 {s.get('grace_count', 0)}"
        f" · 変動 {s.get('changed_count', 0)}"
        f" · 入金差 {s.get('deposit_mismatch_count', 0)}"
        f" · 明細欠 {s.get('deposit_missing_count', 0)}"
        f" · 合算要メモ {s.get('aggregate_need_count', 0)}"
        f" · フォロー下書き {s.get('follow_draft_count', 0)}"
        f" · 入金様子見 {s.get('follow_watch_count', 0)}"
        f" · まもなく {s.get('upcoming_count', 0)} · OK {s.get('ok_count', 0)}"
    )
    for u in s.get("overdue") or []:
        print(f"  ⚠ {u.get('label')}: {u.get('reason')}")
    for u in s.get("grace") or []:
        print(f"  …様子見 {u.get('label')}: {u.get('reason')}")
    for u in s.get("deposit_mismatch") or []:
        print(f"  ≠ {u.get('label')}: {u.get('reason')}")
    for u in s.get("changed") or []:
        print(f"  ↔ {u.get('label')}: {u.get('reason')}")
    for a in s.get("aggregates_need") or []:
        print(f"  ∑ {a.get('title')}: gap={a.get('gap_yen')} memo→ {a.get('memo_key')}")
    for u in s.get("upcoming") or []:
        print(f"  … {u.get('label')}: {u.get('reason')}")
    fd = result.get("follow_drafts") or {}
    for w in fd.get("watching") or []:
        print(f"  …入金様子見 {w.get('manager')} {w.get('label')}: {w.get('reason')}")
    for d in fd.get("drafts") or []:
        print(
            f"  ✉ {d.get('manager')}: {d.get('subject')}（{d.get('item_count')}件）"
        )
    print(f"- 判定: {'✅ 問題なし' if result.get('ok') else '⚠️ 要フォロー'}")
    print("---")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mark-done", action="store_true")
    ap.add_argument("--build-only", action="store_true")
    ap.add_argument("--status", action="store_true")
    ap.add_argument(
        "--no-follow-drafts",
        action="store_true",
        help="入金フォロー下書きを書かない",
    )
    args = ap.parse_args()

    if args.status:
        st = load_json(STATE_PATH)
        print(json.dumps(st.get("last_result") or st, ensure_ascii=False, indent=2))
        return 0

    result = run_build(
        mark_done=args.mark_done or args.build_only,
        write_follow_drafts=not args.no_follow_drafts,
    )
    print_block(result)
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
