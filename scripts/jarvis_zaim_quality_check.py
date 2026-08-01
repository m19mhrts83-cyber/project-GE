#!/usr/bin/env python3
"""
Zaim CSV: 日常買い物の二重取込＋集計設定の食い違いを検知。

  cd ~/git-repos
  python scripts/jarvis_zaim_quality_check.py
  python scripts/jarvis_zaim_quality_check.py --dry-run
  python scripts/jarvis_zaim_quality_check.py --year 2026
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import yaml

JST = ZoneInfo("Asia/Tokyo")
REPO = Path(__file__).resolve().parents[1]
CFG_PATH = REPO / "config" / "zaim_quality_watch.yaml"
OUT_PATH = REPO / ".jarvis_state" / "zaim_quality_watch.json"

INCLUDE = "常に集計に含める"
EXCLUDE = "集計に含めない"


def now_iso() -> str:
    return datetime.now(JST).strftime("%Y-%m-%dT%H:%M:%S%z")


def load_cfg() -> dict[str, Any]:
    return yaml.safe_load(CFG_PATH.read_text(encoding="utf-8")) or {}


def resolve_csv(cfg: dict[str, Any], year: int) -> Path:
    base = Path(cfg.get("csv_base_dir") or "").expanduser()
    return base / f"{year}年度" / f"Zaim.{year}年度.csv"


def nf(s: str) -> str:
    s = unicodedata.normalize("NFKC", (s or "").strip())
    return re.sub(r"\s+", "", s).lower()


def yen(r: dict[str, str]) -> float:
    try:
        return float(r.get("支出") or 0) or 0.0
    except ValueError:
        return 0.0


def shop_key(s: str) -> str:
    s = nf(s)
    for x in ("株式会社", "有限会社", "店", "通信販売", "新経路", "（新経路）", "(新経路)", "豊明"):
        s = s.replace(x, "")
    return s[:24]


def is_card(pay: str, keys: list[str]) -> bool:
    return any(k in (pay or "") for k in keys)


def is_smart(pay: str) -> bool:
    return (pay or "") == "スマートレシート"


def is_daily_shop(shop: str, keywords: list[str]) -> bool:
    s = shop or ""
    return any(k.lower() in s.lower() or k in s for k in keywords)


def is_excluded_shop(shop: str, cat: str, keywords: list[str]) -> bool:
    blob = f"{shop or ''}{cat or ''}"
    return any(k in blob for k in keywords)


def agg_label(r: dict[str, str], include: str, exclude: str) -> str:
    v = (r.get("集計の設定") or "").strip()
    if v == exclude:
        return "exclude"
    if v == include:
        return "include"
    return "unknown"


def find_pairs(
    payments: list[dict[str, str]],
    cfg: dict[str, Any],
) -> list[dict[str, Any]]:
    daily_kw = cfg.get("daily_shop_keywords") or []
    excl_kw = cfg.get("exclude_shop_keywords") or []
    card_kw = cfg.get("card_pay_keywords") or []
    include = cfg.get("include_label") or INCLUDE
    exclude = cfg.get("exclude_label") or EXCLUDE

    smart_agg: dict[tuple[str, str], dict[str, Any]] = defaultdict(
        lambda: {"sum": 0.0, "n": 0, "shop": "", "include_n": 0, "exclude_n": 0}
    )
    for r in payments:
        if not is_smart(r.get("支払元") or ""):
            continue
        shop = r.get("お店") or ""
        if not is_daily_shop(shop, daily_kw):
            continue
        if is_excluded_shop(shop, r.get("カテゴリ") or "", excl_kw):
            continue
        e = yen(r)
        if e == 0:
            continue
        key = (r["日付"], shop_key(shop))
        smart_agg[key]["sum"] += e
        smart_agg[key]["n"] += 1
        smart_agg[key]["shop"] = shop
        lab = agg_label(r, include, exclude)
        if lab == "include":
            smart_agg[key]["include_n"] += 1
        elif lab == "exclude":
            smart_agg[key]["exclude_n"] += 1

    card_rows = [
        r
        for r in payments
        if is_card(r.get("支払元") or "", card_kw)
        and yen(r) > 0
        and not is_excluded_shop(r.get("お店") or "", r.get("カテゴリ") or "", excl_kw)
        and is_daily_shop(r.get("お店") or "", daily_kw)
    ]

    pairs: list[dict[str, Any]] = []
    seen: set[tuple] = set()
    for (d, sk), agg in smart_agg.items():
        if agg["sum"] < 100:
            continue
        dt = datetime.strptime(d, "%Y-%m-%d")
        for r in card_rows:
            rd = r["日付"]
            rdt = datetime.strptime(rd, "%Y-%m-%d")
            if abs((rdt - dt).days) > 1:
                continue
            csk = shop_key(r.get("お店") or "")
            shared = bool(sk and csk and (sk[:6] in csk or csk[:6] in sk))
            if not shared:
                for i in range(max(0, len(sk) - 3)):
                    if sk[i : i + 4] in csk:
                        shared = True
                        break
            if not shared:
                continue
            ce = yen(r)
            if abs(ce - agg["sum"]) > 3:
                continue
            uniq = (d, round(agg["sum"], 0), round(ce, 0), sk[:12], rd)
            if uniq in seen:
                continue
            seen.add(uniq)
            smart_side = (
                "include"
                if agg["include_n"] >= agg["exclude_n"]
                else ("exclude" if agg["exclude_n"] else "unknown")
            )
            card_side = agg_label(r, include, exclude)
            # ルール: smart include, card exclude
            both_include = smart_side == "include" and card_side == "include"
            both_exclude = smart_side == "exclude" and card_side == "exclude"
            rule_ok = smart_side == "include" and card_side == "exclude"
            action = None
            proposal = ""
            if both_include:
                action = {
                    "action": "set_aggregate",
                    "target": "card",
                    "value": "exclude",
                    "date": rd,
                    "shop": r.get("お店") or "",
                    "amount": ce,
                    "pay": (r.get("支払元") or "")[:40],
                }
                proposal = "クレカ側を『集計に含めない』へ（スマートレシートを正）"
            elif both_exclude:
                action = {
                    "action": "set_aggregate",
                    "target": "smart",
                    "value": "include",
                    "date": d,
                    "shop": agg["shop"],
                    "amount": agg["sum"],
                    "pay": "スマートレシート",
                }
                proposal = "スマートレシートを『常に集計に含める』へ（両方除外で実績落ち）"
            elif card_side == "include" and smart_side == "exclude":
                action = {
                    "action": "set_aggregate",
                    "target": "swap_hint",
                    "value": "smart_include_card_exclude",
                    "date": d,
                    "shop": agg["shop"],
                    "amount": agg["sum"],
                    "pay": "",
                }
                proposal = "含む側が逆。スマートを含め、クレカを除外"
            elif rule_ok:
                proposal = "ルールどおり（明細含める・クレカ除外）"

            pairs.append(
                {
                    "date": d,
                    "card_date": rd,
                    "shop": agg["shop"],
                    "card_shop": r.get("お店") or "",
                    "smart_yen": round(agg["sum"], 0),
                    "smart_n": agg["n"],
                    "card_yen": round(ce, 0),
                    "pay": (r.get("支払元") or "")[:40],
                    "smart_agg": smart_side,
                    "card_agg": card_side,
                    "rule_ok": rule_ok,
                    "both_include": both_include,
                    "both_exclude": both_exclude,
                    "proposal": proposal,
                    "action": action,
                    "card_category": (r.get("カテゴリ") or "")[:40],
                }
            )
    return pairs


def check_amazon(
    payments: list[dict[str, str]], cfg: dict[str, Any]
) -> list[dict[str, Any]]:
    include = cfg.get("include_label") or INCLUDE
    exclude = cfg.get("exclude_label") or EXCLUDE
    card_kw = cfg.get("card_pay_keywords") or []
    issues: list[dict[str, Any]] = []

    site = [
        r
        for r in payments
        if (r.get("支払元") or "") == "Amazon.co.jp" and yen(r) > 0
    ]
    card_amz = [
        r
        for r in payments
        if is_card(r.get("支払元") or "", card_kw)
        and "amazon" in nf(r.get("お店") or "")
        and yen(r) > 0
    ]

    # same day ±1, similar amount
    for s in site:
        sd = s["日付"]
        se = yen(s)
        sdt = datetime.strptime(sd, "%Y-%m-%d")
        for c in card_amz:
            cdt = datetime.strptime(c["日付"], "%Y-%m-%d")
            if abs((cdt - sdt).days) > 2:
                continue
            ce = yen(c)
            if abs(ce - se) > 3:
                continue
            sa = agg_label(s, include, exclude)
            ca = agg_label(c, include, exclude)
            if sa == "include" and ca == "exclude":
                continue  # OK
            proposal = ""
            action = None
            if sa == "include" and ca == "include":
                proposal = "Amazon 二重集計。クレカ側を『含めない』へ"
                action = {
                    "action": "set_aggregate",
                    "target": "card",
                    "value": "exclude",
                    "date": c["日付"],
                    "shop": c.get("お店") or "",
                    "amount": ce,
                    "pay": (c.get("支払元") or "")[:40],
                }
            elif sa == "exclude" and ca == "include":
                proposal = "含む側が逆。サイト連携を含め、クレカを除外"
            elif sa == "exclude" and ca == "exclude":
                proposal = "両方除外。サイト連携を『含める』へ"
                action = {
                    "action": "set_aggregate",
                    "target": "amazon_site",
                    "value": "include",
                    "date": sd,
                    "shop": s.get("お店") or "Amazon.co.jp",
                    "amount": se,
                    "pay": "Amazon.co.jp",
                }
            else:
                continue
            issues.append(
                {
                    "kind": "amazon_dual",
                    "date": sd,
                    "site_yen": se,
                    "card_yen": ce,
                    "site_agg": sa,
                    "card_agg": ca,
                    "proposal": proposal,
                    "action": action,
                }
            )
    return issues


def check_must_include(
    payments: list[dict[str, str]], cfg: dict[str, Any]
) -> list[dict[str, Any]]:
    include = cfg.get("include_label") or INCLUDE
    exclude = cfg.get("exclude_label") or EXCLUDE
    out: list[dict[str, Any]] = []
    for rule in cfg.get("must_include") or []:
        shop_kw = rule.get("shop_keywords") or []
        pay_kw = rule.get("pay_keywords") or []
        for r in payments:
            shop = r.get("お店") or ""
            pay = r.get("支払元") or ""
            blob = shop + pay + (r.get("品目") or "")
            if shop_kw and not any(k in blob for k in shop_kw):
                continue
            if pay_kw and not any(k in pay for k in pay_kw):
                continue
            if yen(r) <= 0 and float(r.get("振替") or 0) == 0:
                # payment only with expense; also allow if 支出
                if yen(r) == 0:
                    continue
            if agg_label(r, include, exclude) != "exclude":
                continue
            out.append(
                {
                    "kind": "must_include",
                    "rule_id": rule.get("id"),
                    "description": rule.get("description"),
                    "date": r.get("日付"),
                    "shop": shop,
                    "pay": pay[:40],
                    "amount": yen(r),
                    "proposal": f"{rule.get('description')}: 『常に集計に含める』へ変更を提案",
                    "action": {
                        "action": "set_aggregate",
                        "target": "must_include",
                        "value": "include",
                        "date": r.get("日付"),
                        "shop": shop,
                        "amount": yen(r),
                        "pay": pay[:40],
                    },
                }
            )
    return out


def build_result(
    pairs: list[dict[str, Any]],
    amazon: list[dict[str, Any]],
    must: list[dict[str, Any]],
    cfg: dict[str, Any],
    csv_path: Path,
) -> dict[str, Any]:
    thr = float(cfg.get("attention_dup_yen") or 50000)
    both_inc = [p for p in pairs if p.get("both_include")]
    both_exc = [p for p in pairs if p.get("both_exclude")]
    ok_pairs = [p for p in pairs if p.get("rule_ok")]
    dup_yen = sum(p["card_yen"] for p in both_inc)
    shop_c = Counter(shop_key(p["shop"]) for p in both_inc)

    level = "ok"
    if both_exc or amazon or (pairs and not both_inc and not ok_pairs):
        level = "warn"
    if both_inc or must or dup_yen >= thr:
        level = "attention"
    if not pairs and not amazon and not must:
        level = "ok"

    parts = [
        f"日常ペア {len(pairs)}",
        f"ルールOK {len(ok_pairs)}",
        f"両方含める {len(both_inc)}（¥{dup_yen:,.0f}）",
    ]
    if both_exc:
        parts.append(f"両方除外 {len(both_exc)}")
    if must:
        parts.append(f"must含めない {len(must)}")
    if amazon:
        parts.append(f"Amazon二重疑い {len(amazon)}")

    samples = []
    for p in both_inc[:8]:
        samples.append({**p, "severity": "both_include"})
    for p in both_exc[:3]:
        samples.append({**p, "severity": "both_exclude"})
    for a in amazon[:5]:
        samples.append(a)
    for m in must[:5]:
        samples.append(m)
    # also show a few OK for context
    for p in ok_pairs[:3]:
        samples.append({**p, "severity": "rule_ok"})

    actions = [s["action"] for s in samples if s.get("action")]

    detail_bits = []
    if shop_c:
        detail_bits.append(
            "両方含める店: "
            + ", ".join(f"{k}×{v}" for k, v in shop_c.most_common(5))
        )
    if ok_pairs:
        detail_bits.append(f"クレカ除外でOK例あり（{len(ok_pairs)}件）")
    for m in must[:3]:
        detail_bits.append(m.get("proposal") or "")

    return {
        "updated_at": now_iso(),
        "csv": str(csv_path),
        "level": level,
        "summary": " · ".join(parts),
        "detail": " / ".join(x for x in detail_bits if x),
        "pair_count": len(pairs),
        "rule_ok_count": len(ok_pairs),
        "both_include_count": len(both_inc),
        "both_exclude_count": len(both_exc),
        "dup_yen_both_include": dup_yen,
        "amazon_issues": len(amazon),
        "must_include_violations": len(must),
        "top_shops_both_include": dict(shop_c.most_common(8)),
        "samples": samples,
        "proposed_actions": actions,
    }


def run(year: int | None = None) -> dict[str, Any]:
    cfg = load_cfg()
    y = year or datetime.now(JST).year
    csv_path = resolve_csv(cfg, y)
    if not csv_path.is_file():
        # fallback previous year
        csv_path = resolve_csv(cfg, y - 1)
    if not csv_path.is_file():
        return {
            "updated_at": now_iso(),
            "level": "attention",
            "summary": f"Zaim CSV なし（{y}）",
            "detail": str(resolve_csv(cfg, y)),
            "samples": [],
            "proposed_actions": [],
        }

    rows = list(csv.DictReader(csv_path.open(encoding="utf-8-sig")))
    payments = [r for r in rows if r.get("方法") == "payment"]
    pairs = find_pairs(payments, cfg)
    amazon = check_amazon(payments, cfg)
    must = check_must_include(payments, cfg)
    return build_result(pairs, amazon, must, cfg, csv_path)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--year", type=int, default=None)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    result = run(args.year)
    if not args.dry_run:
        OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        OUT_PATH.write_text(
            json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(f"# wrote {OUT_PATH}", file=sys.stderr)
    print(
        f"# level={result.get('level')} {result.get('summary')}",
        file=sys.stderr,
    )
    if args.json or args.dry_run:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
