#!/usr/bin/env python3
"""Jarvis 月次 Vポイント確認 — 付与サマリ（日次／月次・％別）＋ウィンドウC。

使い方:
  python scripts/jarvis_vpoint_monthly_check.py
  python scripts/jarvis_vpoint_monthly_check.py --mark-done
  python scripts/jarvis_vpoint_monthly_check.py --mark-done --target-month 2026-07
  python scripts/jarvis_vpoint_monthly_check.py --status
  python scripts/jarvis_vpoint_monthly_check.py --build-summary-only --target-month 2026-07
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

JST = ZoneInfo("Asia/Tokyo")
REPO = Path(__file__).resolve().parents[1]
STATE_DIR = REPO / ".jarvis_state"
STATE_PATH = STATE_DIR / "vpoint_monthly.json"
EXAMPLE_PATH = STATE_DIR / "vpoint_monthly.example.json"
RESULT_PATH = STATE_DIR / "vpoint_audit_result.json"
EXPECT_PATH = STATE_DIR / "vpoint_audit_expectations.json"
PRIVATE_ENV = REPO / ".env.jarvis_private"
HISTORY_GLOB = "vpoint_tsite_history_*.json"

DEFAULT_TSUMITATE_YEN = 90_000

MONTHLY_KW = (
    "投信積立カード決済特典",
    "選べる特典",
    "給与特典",
    "資産運用特典",
    "Ｖポイントアップ",
    "Vポイントアップ",
)
DAILY_RATE_RE = re.compile(
    r"[＋+]?\s*([0-9０-９]+)\s*[％%]|プラス\s*([0-9０-９]+)\s*[％%]"
)
ZEN_DIGITS = str.maketrans("０１２３４５６７８９", "0123456789")


def load_dotenv(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.is_file():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.+?)\s*$", line)
        if m and not line.lstrip().startswith("#"):
            out[m.group(1)] = m.group(2).strip().strip("\"'")
    return out


def load_json(path: Path, default: dict | None = None) -> dict:
    if path.is_file():
        return json.loads(path.read_text(encoding="utf-8"))
    return default if default is not None else {}


def save_state(state: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(
        json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def in_window_c(now: datetime) -> bool:
    return now.day >= 25


def month_key(now: datetime) -> str:
    return now.strftime("%Y-%m")


def prev_month_key(now: datetime) -> str:
    y, m = now.year, now.month
    if m == 1:
        return f"{y - 1}-12"
    return f"{y}-{m - 1:02d}"


def latest_history() -> dict | None:
    files = sorted(
        STATE_DIR.glob(HISTORY_GLOB), key=lambda p: p.stat().st_mtime, reverse=True
    )
    for p in files:
        data = load_json(p)
        if data:
            data["_path"] = str(p)
            return data
    return None


def _to_int(v: Any) -> int | None:
    if v is None:
        return None
    if isinstance(v, bool):
        return None
    if isinstance(v, int):
        return v
    if isinstance(v, float) and not math.isnan(v):
        return int(v)
    s = str(v).replace(",", "").translate(ZEN_DIGITS).strip()
    if re.fullmatch(r"-?\d+", s):
        return int(s)
    return None


def _entry_month(e: dict) -> str | None:
    d = str(e.get("date") or "")
    m = re.match(r"^(\d{4})[-/](\d{2})", d)
    if m:
        return f"{m.group(1)}-{m.group(2)}"
    m2 = re.match(r"^(\d{2})/(\d{2})/(\d{2})", d)  # YY/MM/DD
    if m2:
        yy = int(m2.group(1))
        return f"{2000 + yy}-{m2.group(2)}"
    return None


def classify_cadence(desc: str) -> str:
    for kw in MONTHLY_KW:
        if kw in desc:
            return "monthly"
    if DAILY_RATE_RE.search(desc) or "モバイルオーダー" in desc or "対象店" in desc:
        return "daily"
    if "ポイント" in desc or "ご利用" in desc:
        return "daily"
    return "other"


def parse_rate_from_desc(desc: str) -> float | None:
    m = DAILY_RATE_RE.search(desc)
    if not m:
        return None
    raw = (m.group(1) or m.group(2) or "").translate(ZEN_DIGITS)
    try:
        return float(raw)
    except ValueError:
        return None


def rate_for_entry(
    e: dict, *, tsumitate_yen: int, cadence: str
) -> float | None:
    desc = str(e.get("desc") or "")
    explicit = parse_rate_from_desc(desc)
    if explicit is not None:
        return explicit
    pt = _to_int(e.get("pt"))
    yen = _to_int(e.get("yen"))
    if cadence == "monthly" and "投信積立" in desc and pt is not None and tsumitate_yen > 0:
        return round(100.0 * pt / tsumitate_yen, 2)
    if pt is not None and yen is not None and yen > 0:
        return round(100.0 * pt / yen, 2)
    return None


def entries_from_audit_fallback(audit: dict, target_month: str) -> list[dict]:
    """Tサイト生履歴が無いとき監査結果から最低限の行を合成。"""
    out: list[dict] = []
    ct = audit.get("credit_tsumitate") or {}
    ph = ct.get("point_history") or {}
    for b in ph.get("tsumitate_bonus_recent") or []:
        if not isinstance(b, dict):
            continue
        d = str(b.get("date") or "")
        if not d.startswith(target_month):
            continue
        pt = _to_int(b.get("pt"))
        rate = b.get("rate_vs_90k")
        rate_pct = round(float(rate) * 100, 2) if isinstance(rate, (int, float)) else None
        label = str(b.get("label") or "投信積立カード決済特典")
        out.append(
            {
                "date": d,
                "desc": f"投信積立カード決済特典（{label}）",
                "pt": pt,
                "yen": DEFAULT_TSUMITATE_YEN,
                "rate_hint": rate_pct,
                "_source": "audit_fallback",
            }
        )
    mer = audit.get("merchant_high_rate") or {}
    te = mer.get("tsite_evidence") or {}
    for k, v in te.items():
        if k == "note" or not isinstance(v, (int, float)):
            continue
        m = re.search(r"(20\d{2})(\d{2})(\d{2})", k)
        if not m:
            continue
        d = f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
        if not d.startswith(target_month):
            continue
        name = "対象店＋６％特典"
        if "mcdonald" in k.lower():
            name = "マクドナルドモバイルオーダー ＋６％特典"
        elif "saizeriya" in k.lower() or "サイゼ" in k:
            name = "サイゼリヤ ＋６％特典"
        out.append(
            {
                "date": d,
                "desc": name,
                "pt": int(v),
                "yen": None,
                "_source": "audit_fallback",
            }
        )
    return out


def build_grant_summary(
    entries: list[dict],
    audit: dict,
    target_month: str,
    *,
    tsumitate_yen: int | None = None,
    source_note: str = "",
) -> dict[str, Any]:
    yen_base = tsumitate_yen or (
        (audit.get("credit_tsumitate") or {}).get("monthly_yen_confirmed")
    ) or DEFAULT_TSUMITATE_YEN
    yen_base = int(yen_base)

    filtered: list[dict] = []
    for e in entries:
        if not isinstance(e, dict):
            continue
        em = _entry_month(e)
        if em and em != target_month:
            continue
        if not em and not str(e.get("date") or "").startswith(target_month):
            # keep audit_fallback without month only if date starts with target
            if e.get("_source") != "audit_fallback":
                continue
        filtered.append(e)

    by_cadence = {"monthly": 0, "daily": 0, "other": 0}
    rate_buckets: dict[str, dict[str, Any]] = {}
    specials: list[dict[str, Any]] = []
    total_pt = 0
    classified: list[dict[str, Any]] = []

    for e in filtered:
        desc = str(e.get("desc") or "")
        pt = _to_int(e.get("pt")) or 0
        cadence = classify_cadence(desc)
        rate = e.get("rate_hint")
        if rate is None:
            rate = rate_for_entry(e, tsumitate_yen=yen_base, cadence=cadence)
        by_cadence[cadence] = by_cadence.get(cadence, 0) + pt
        total_pt += pt
        key = "unknown" if rate is None else str(rate)
        bucket = rate_buckets.setdefault(
            key,
            {"rate_pct": rate, "pt": 0, "count": 0, "samples": []},
        )
        bucket["pt"] += pt
        bucket["count"] += 1
        if len(bucket["samples"]) < 3:
            bucket["samples"].append(
                {"date": e.get("date"), "desc": desc[:60], "pt": pt}
            )
        row = {
            "date": e.get("date"),
            "desc": desc[:80],
            "pt": pt,
            "cadence": cadence,
            "rate_pct": rate,
        }
        classified.append(row)
        if rate is not None and (rate > 1.0 or parse_rate_from_desc(desc) is not None):
            specials.append(row)

    by_rate = sorted(
        rate_buckets.values(),
        key=lambda b: (
            b["rate_pct"] is None,
            -(b["rate_pct"] or 0),
            -b["pt"],
        ),
    )

    insights: list[str] = []
    for s in specials[:6]:
        insights.append(
            f"特別％ {s['rate_pct']}%: {s['desc']}（{s['pt']}pt）"
            if s.get("rate_pct") is not None
            else f"特別付与: {s['desc']}（{s['pt']}pt）"
        )

    rate_info = (audit.get("credit_tsumitate") or {}).get("effective_rate") or {}
    merchant = audit.get("merchant_high_rate") or {}
    shop_up_ok = True
    condition_grants_ok = True

    if rate_info.get("status") in (
        "confirmed_1pct_not_6pct",
        "not_yet_verifiable_as_6pct",
    ):
        condition_grants_ok = False
        insights.append(
            "意図外: クレカ積立特典が1%帯のまま（最大6%条件未達の可能性）"
        )
    id_note = str(
        (merchant.get("meisai_202608_sample") or {}).get("note")
        or merchant.get("verdict")
        or ""
    )
    if "ｉＤ" in id_note or "iD" in id_note:
        shop_up_ok = False
        insights.append(
            "意図外: 対象店まわりの明細に／ｉＤが多く、高還元（Visaタッチ想定）が未適用の疑い"
        )
    te = merchant.get("tsite_evidence") or {}
    if te.get("mcdonalds_plus6pct_20260724") or any(
        "＋６％" in str(x.get("desc") or "") or "+6" in str(x.get("desc") or "")
        for x in classified
        if x.get("cadence") == "daily"
    ):
        insights.append(
            "対象店アップ: モバイルオーダー等で＋6%付与の実績あり（正しいレール）"
        )
    if by_cadence["monthly"] == 0 and target_month:
        insights.append("月次条件系の付与行が当月サマリに無い（未取得または未付与）")
        condition_grants_ok = False

    if not insights:
        insights.append("特記事項なし（取得範囲内）")

    return {
        "target_month": target_month,
        "total_pt": total_pt,
        "by_cadence": by_cadence,
        "by_rate": by_rate,
        "insights": insights[:10],
        "shop_up_ok": shop_up_ok,
        "condition_grants_ok": condition_grants_ok,
        "tsumitate_yen": yen_base,
        "entry_count": len(filtered),
        "source_note": source_note
        or ("Tサイト履歴" if filtered and not any(e.get("_source") == "audit_fallback" for e in filtered) else "監査結果フォールバック"),
        "at": datetime.now(JST).isoformat(timespec="seconds"),
        "grant_rule": "ウィンドウC（25日〜月末）に月次サマリ更新。付与は日次利用と月次条件が混在",
    }


def upsert_grant_history(state: dict, summary: dict) -> None:
    target = summary.get("target_month")
    if not target:
        return
    entry = {
        "target_month": target,
        "total_pt": summary.get("total_pt"),
        "by_cadence": summary.get("by_cadence"),
        "insights": (summary.get("insights") or [])[:5],
        "shop_up_ok": summary.get("shop_up_ok"),
        "condition_grants_ok": summary.get("condition_grants_ok"),
        "at": summary.get("at"),
        "source_note": summary.get("source_note"),
    }
    hist = [h for h in (state.get("grant_history") or []) if isinstance(h, dict)]
    hist = [h for h in hist if h.get("target_month") != target]
    hist.append(entry)
    hist.sort(key=lambda h: str(h.get("target_month") or ""), reverse=True)
    state["grant_history"] = hist[:24]


def build_report(state: dict, result: dict, env: dict[str, str], now: datetime) -> dict:
    mk = month_key(now)
    last = state.get("last_check_c")
    done = last == mk
    align = result.get("alignment_2026_07_30") or {}
    tsite_env = bool(env.get("VPOINT_TSITE_ID"))
    tsite_status = "ready_id" if tsite_env else "pending_user"
    bal = (
        result.get("credit_tsumitate", {}).get("point_history", {}) or {}
    ).get("balance_pt")
    if bal is None:
        bal = result.get("credit_tsumitate", {}).get("vpoint_balance_2026_07_29")
    tsumi = result.get("credit_tsumitate", {}).get("monthly_yen_confirmed")
    rate = result.get("credit_tsumitate", {}).get("effective_rate", {})
    merchant = result.get("merchant_high_rate", {})
    id_note = (merchant.get("meisai_202608_sample") or {}).get("note") or merchant.get("verdict") or ""
    warnings: list[str] = []
    if not tsite_env:
        warnings.append("Tサイト認証待ち（VPOINT_TSITE_ID）")
    if rate.get("status") in (
        "not_yet_verifiable_as_6pct",
        "confirmed_1pct_not_6pct",
    ):
        warnings.append("クレカ積立は1%実績／6%未達")
    if "ｉＤ" in id_note or "iD" in id_note:
        warnings.append("明細に／ｉＤが多い（高還元対象外レール）")

    ok = len(warnings) == 0
    return {
        "window": "C",
        "month": mk,
        "in_window": in_window_c(now),
        "already_done": done,
        "ok": ok,
        "tsumitate_yen": tsumi,
        "vpoint_balance": bal,
        "id_rail_note": id_note[:160],
        "tsite_status": tsite_status,
        "rate_status": rate.get("status"),
        "warnings": warnings,
        "alignment_ops": (align.get("ops") or {}),
    }


def format_block(s: dict, grant: dict | None = None) -> str:
    judge = "✅ 問題なし" if s["ok"] else "⚠️ 要フォロー: " + " / ".join(s["warnings"])
    lines = [
        "---",
        f"📎 月次確認（Vポイント）— ウィンドウC / {s['month']}",
        f"- クレカ積立: {s['tsumitate_yen'] or '—'}円/月想定（直近監査）",
        f"- Vポイント残高（直近監査）: {s['vpoint_balance'] if s['vpoint_balance'] is not None else '—'}",
        f"- 決済レール: {s['id_rail_note'] or '—'}",
        f"- Tサイト: {s['tsite_status']}",
        f"- 積立還元率: {s['rate_status'] or '—'}",
        f"- 判定: {judge}",
    ]
    if grant:
        bc = grant.get("by_cadence") or {}
        lines.append(
            f"- 付与サマリ（{grant.get('target_month')}）: 合計 {grant.get('total_pt')}pt"
            f" ／ 月次条件 {bc.get('monthly', 0)}pt ／ 日次 {bc.get('daily', 0)}pt"
        )
        for ins in (grant.get("insights") or [])[:3]:
            lines.append(f"  · {ins}")
    lines.append("- 注: 月次は深い突合。日常は cadence／Wallet強制変更なし")
    lines.append("---")
    return "\n".join(lines)


def collect_entries_for_month(audit: dict, target_month: str) -> tuple[list[dict], str]:
    hist = latest_history()
    entries: list[dict] = []
    note = ""
    if hist:
        entries = list(hist.get("key_entries") or [])
        note = f"Tサイト履歴 {Path(hist.get('_path') or '').name}"
    month_entries = [
        e
        for e in entries
        if isinstance(e, dict)
        and (
            _entry_month(e) == target_month
            or str(e.get("date") or "").startswith(target_month)
        )
    ]
    if month_entries:
        return month_entries, note
    fb = entries_from_audit_fallback(audit, target_month)
    return fb, "監査結果フォールバック（Tサイト当月行なし）"


def main() -> int:
    ap = argparse.ArgumentParser(description="Jarvis Vポイント月次確認")
    ap.add_argument("--mark-done", action="store_true", help="当月ウィンドウCを実施済みにする")
    ap.add_argument("--status", action="store_true", help="ウィンドウ該当・実施済のみ表示")
    ap.add_argument(
        "--target-month",
        default="",
        help="付与サマリ対象月 YYYY-MM（未指定時は前月）",
    )
    ap.add_argument(
        "--build-summary-only",
        action="store_true",
        help="サマリだけ生成して state に書く（ウィンドウチェック無視）",
    )
    args = ap.parse_args()

    env = load_dotenv(PRIVATE_ENV)
    if env.get("JARVIS_VPOINT_MONTHLY_DISABLE") == "1":
        print("📎 Vポイント月次: 無効化（JARVIS_VPOINT_MONTHLY_DISABLE=1）")
        return 0

    state = load_json(STATE_PATH)
    if not state:
        state = load_json(EXAMPLE_PATH, {"disabled": False})
    if state.get("disabled"):
        print("📎 Vポイント月次: 無効化（vpoint_monthly.json disabled）")
        return 0

    now = datetime.now(JST)
    result = load_json(RESULT_PATH)
    summary = build_report(state, result, env, now)
    target = args.target_month.strip() or prev_month_key(now)
    entries, src_note = collect_entries_for_month(result, target)
    grant = build_grant_summary(
        entries,
        result,
        target,
        tsumitate_yen=_to_int(summary.get("tsumitate_yen")),
        source_note=src_note,
    )

    if args.status:
        print(
            json.dumps(
                {
                    "in_window_c": summary["in_window"],
                    "month": summary["month"],
                    "last_check_c": state.get("last_check_c"),
                    "already_done": summary["already_done"],
                    "should_run": summary["in_window"] and not summary["already_done"],
                    "grant_target": target,
                    "grant_total_pt": grant.get("total_pt"),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    print(format_block(summary, grant))
    print()
    print(
        json.dumps(
            {
                "in_window_c": summary["in_window"],
                "already_done": summary["already_done"],
                "should_run": summary["in_window"] and not summary["already_done"],
                "summary": summary,
                "grant_summary": grant,
            },
            ensure_ascii=False,
            indent=2,
        )
    )

    if args.mark_done or args.build_summary_only:
        if args.mark_done:
            state["last_check_c"] = summary["month"]
        state["last_result_c"] = {
            "at": now.isoformat(timespec="seconds"),
            "ok": summary["ok"],
            "tsumitate_yen": summary["tsumitate_yen"],
            "vpoint_balance": summary["vpoint_balance"],
            "id_rail_note": summary["id_rail_note"],
            "tsite_status": summary["tsite_status"],
            "note": "; ".join(summary["warnings"]) if summary["warnings"] else "ok",
            "target_month": target,
            "grant_summary": grant,
        }
        upsert_grant_history(state, grant)
        # ack は触らない
        save_state(state)
        print(f"\n✅ grant_summary target={target} total_pt={grant.get('total_pt')}")
        if args.mark_done:
            print(f"✅ marked last_check_c={summary['month']}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
