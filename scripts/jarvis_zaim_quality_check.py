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

sys.path.insert(0, str(Path(__file__).resolve().parent))
import jarvis_zaim_learn as zlearn  # noqa: E402

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


def suggest_category(shop: str, item: str, rules: list[dict[str, Any]]) -> str | None:
    return zlearn.suggest_from_yaml(shop, item, rules)


def check_category_reviews(
    payments: list[dict[str, str]],
    cfg: dict[str, Any],
) -> list[dict[str, Any]]:
    """費目が『その他／使途不明』等の直近行を列挙。high は runner が Web 自動適用。"""
    cr = cfg.get("category_review") or {}
    days = int(cr.get("lookback_days") or 14)
    max_items = int(cr.get("max_items") or 25)
    suspicious = list(cr.get("suspicious_substrings") or ["その他", "使途不明"])
    yaml_rules = list(cr.get("suggest_rules") or [])
    learn_rules = zlearn.load_rules()
    since = date.today() - timedelta(days=days)
    out: list[dict[str, Any]] = []
    for r in payments:
        raw_d = (r.get("日付") or "").strip()[:10]
        try:
            d = date.fromisoformat(raw_d.replace("/", "-"))
        except ValueError:
            continue
        if d < since:
            continue
        cat = (r.get("カテゴリ") or "").strip()
        if not zlearn.is_suspicious(cat, suspicious):
            continue
        amount = yen(r)
        if amount == 0:
            continue
        shop = (r.get("お店") or "").strip()
        item = (r.get("品目") or "").strip()
        pay = (r.get("支払元") or "")[:40]
        method = (r.get("方法") or "payment").strip()
        resolved = zlearn.resolve_suggestion(
            shop, item, yaml_rules=yaml_rules, rules=learn_rules
        )
        suggest = resolved.get("suggest")
        genre = str(resolved.get("genre") or "")
        confidence = str(resolved.get("confidence") or "low")
        if not suggest:
            confidence = "low"
        proposal = (
            f"費目見直し: {cat} → {suggest}（{confidence}）"
            if suggest
            else f"費目見直し: {cat}（提案なし・要目視）"
        )
        action_name = "set_category" if suggest and confidence == "high" else "category_review"
        row = {
            "kind": "category_review",
            "date": d.isoformat(),
            "shop": shop or item or "—",
            "item": item,
            "amount": amount,
            "category": cat,
            "genre": (r.get("カテゴリの内訳") or "").strip(),
            "suggest": suggest,
            "suggest_genre": genre,
            "confidence": confidence,
            "learn_key": resolved.get("learn_key"),
            "suggest_source": resolved.get("source"),
            "pay": pay,
            "method": method,
            "row_key": zlearn.row_key(
                {
                    "日付": d.isoformat(),
                    "支出": amount,
                    "お店": shop,
                    "支払元": pay,
                    "方法": method,
                    "amount": amount,
                    "shop": shop,
                    "pay": pay,
                    "date": d.isoformat(),
                    "method": method,
                }
            ),
            "proposal": proposal,
            "action": {
                "action": action_name,
                "target": "category",
                "value": suggest or "review",
                "genre": genre,
                "date": d.isoformat(),
                "shop": shop or item,
                "item": item,
                "amount": amount,
                "pay": pay,
                "method": method,
                "category": cat,
                "suggest": suggest,
                "confidence": confidence,
                "learn_key": resolved.get("learn_key"),
            },
        }
        out.append(row)
    high = [x for x in out if x.get("confidence") == "high"]
    low = [x for x in out if x.get("confidence") != "high"]
    high.sort(key=lambda x: x.get("date") or "", reverse=True)
    low.sort(key=lambda x: x.get("date") or "", reverse=True)
    return (high + low)[:max_items]


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
    category_reviews: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    thr = float(cfg.get("attention_dup_yen") or 50000)
    both_inc = [p for p in pairs if p.get("both_include")]
    both_exc = [p for p in pairs if p.get("both_exclude")]
    ok_pairs = [p for p in pairs if p.get("rule_ok")]
    cats = list(category_reviews or [])
    dup_yen = sum(p["card_yen"] for p in both_inc)
    shop_c = Counter(shop_key(p["shop"]) for p in both_inc)

    level = "ok"
    if both_exc or amazon or (pairs and not both_inc and not ok_pairs):
        level = "warn"
    if both_inc or must or dup_yen >= thr:
        level = "attention"
    if cats and level == "ok":
        level = "info"
    if not pairs and not amazon and not must and not cats:
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
    if cats:
        high_n = sum(1 for c in cats if c.get("confidence") == "high")
        parts.append(f"費目見直し {len(cats)}" + (f"（自動可 {high_n}）" if high_n else ""))

    samples = []
    for p in both_inc[:8]:
        samples.append({**p, "viewpoint": "both_include"})
    for p in both_exc[:3]:
        samples.append({**p, "viewpoint": "both_exclude"})
    for a in amazon[:5]:
        samples.append(a)
    for m in must[:5]:
        samples.append(m)
    for p in ok_pairs[:3]:
        samples.append({**p, "viewpoint": "rule_ok"})

    actions = [s["action"] for s in samples if s.get("action")]

    def _yen(s: dict) -> float:
        act = s.get("action") if isinstance(s.get("action"), dict) else {}
        for k in ("amount", "smart_yen", "card_yen", "yen"):
            if act.get(k) is not None:
                try:
                    return float(act[k])
                except (TypeError, ValueError):
                    pass
            if s.get(k) is not None:
                try:
                    return float(s[k])
                except (TypeError, ValueError):
                    pass
        return 0.0

    def _action_row(s: dict) -> dict:
        act = s.get("action") if isinstance(s.get("action"), dict) else {}
        date = str(act.get("date") or s.get("date") or s.get("card_date") or "")
        shop = str(act.get("shop") or s.get("shop") or s.get("card_shop") or "")
        amount = _yen(s)
        proposal = str(s.get("proposal") or "").strip()
        kind = str(s.get("viewpoint") or s.get("kind") or "")
        line = f"{date} / {shop} / ¥{amount:,.0f}"
        if proposal:
            line = f"{line} / {proposal}"
        return {
            "date": date,
            "shop": shop,
            "amount": amount,
            "proposal": proposal,
            "kind": kind,
            "line": line,
            "action": act or None,
        }

    seen: set[str] = set()
    action_items: list[dict] = []
    action_lines: list[str] = []
    for s in both_inc + both_exc + amazon + must:
        row = _action_row({**s, "viewpoint": s.get("viewpoint") or (
            "both_include" if s.get("both_include") else
            "both_exclude" if s.get("both_exclude") else
            s.get("kind") or ""
        )})
        key = f"{row['date']}|{row['shop']}|{row['amount']}"
        if key in seen or not row["date"]:
            continue
        seen.add(key)
        action_items.append(row)
        action_lines.append(row["line"])

    detail_bits = []
    if action_lines:
        detail_bits.append("要対応:\n" + "\n".join(f"- {ln}" for ln in action_lines[:20]))
    if cats:
        detail_bits.append(
            "費目見直し:\n"
            + "\n".join(
                f"- {c.get('date')} / {c.get('shop')} / ¥{float(c.get('amount') or 0):,.0f} / {c.get('proposal')}"
                for c in cats[:15]
            )
        )
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
        "detail": "\n".join(x for x in detail_bits if x),
        "action_lines": action_lines,
        "action_items": action_items,
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
        "category_reviews": cats,
        "category_review_count": len(cats),
    }


def run(year: int | None = None) -> dict[str, Any]:
    cfg = load_cfg()
    y = year or datetime.now(JST).year
    csv_path = resolve_csv(cfg, y)
    if not csv_path.is_file():
        csv_path = resolve_csv(cfg, y - 1)
    if not csv_path.is_file():
        return {
            "updated_at": now_iso(),
            "level": "attention",
            "summary": f"Zaim CSV なし（{y}）",
            "detail": str(resolve_csv(cfg, y)),
            "samples": [],
            "proposed_actions": [],
            "category_reviews": [],
            "category_review_count": 0,
        }

    rows = list(csv.DictReader(csv_path.open(encoding="utf-8-sig")))
    payments = [r for r in rows if r.get("方法") == "payment"]
    pairs = find_pairs(payments, cfg)
    amazon = check_amazon(payments, cfg)
    must = check_must_include(payments, cfg)
    cats = check_category_reviews(payments, cfg)
    return build_result(pairs, amazon, must, cfg, csv_path, cats)


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
