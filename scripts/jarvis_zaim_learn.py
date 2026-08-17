#!/usr/bin/env python3
"""
Zaim 費目学習: 前回スナップショット × 今回 CSV の差分からルールを更新する。

  cd ~/git-repos && set -a && source .env.jarvis_private && set +a
  python scripts/jarvis_zaim_learn.py
  python scripts/jarvis_zaim_learn.py --dry-run --json
  python scripts/jarvis_zaim_learn.py --self-test

Watch runner の先頭で呼ぶ。自動適用は count>=2 かつ conflict/suppressed なし。
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import yaml

JST = ZoneInfo("Asia/Tokyo")
REPO = Path(__file__).resolve().parents[1]
STATE = REPO / ".jarvis_state"
CFG_PATH = REPO / "config" / "zaim_quality_watch.yaml"
RULES_PATH = STATE / "zaim_learn_rules.json"
SNAPSHOT_PATH = STATE / "zaim_learn_snapshot.json"
LAST_PATH = STATE / "zaim_learn_last.json"
CHANGELOG_PATH = STATE / "zaim_watch_changelog.json"
AUTO_MIN_DEFAULT = 2


def now_iso() -> str:
    return datetime.now(JST).strftime("%Y-%m-%dT%H:%M:%S%z")


def nf(s: str) -> str:
    s = unicodedata.normalize("NFKC", (s or "").strip())
    return re.sub(r"\s+", "", s).lower()


def shop_key(s: str) -> str:
    s = nf(s)
    for x in ("株式会社", "有限会社", "店", "通信販売", "新経路", "（新経路）", "(新経路)", "豊明"):
        s = s.replace(x, "")
    return s[:24]


def yen_of(r: dict[str, str]) -> float:
    try:
        return float(r.get("支出") or 0) or 0.0
    except ValueError:
        return 0.0


def learn_key(shop: str, item: str = "") -> str:
    sk = shop_key(shop)
    if sk:
        return sk
    return shop_key(item)


def row_key(r: dict[str, str] | dict[str, Any]) -> str:
    date = str(r.get("日付") or r.get("date") or "")[:10].replace("/", "-")
    try:
        amt = int(round(float(r.get("支出") or r.get("amount") or 0)))
    except (TypeError, ValueError):
        amt = 0
    shop = str(r.get("お店") or r.get("shop") or "").strip()
    pay = str(r.get("支払元") or r.get("pay") or "").strip()
    method = str(r.get("方法") or r.get("method") or "payment").strip()
    return f"{date}|{amt}|{shop}|{pay}|{method}"


def load_cfg() -> dict[str, Any]:
    if not CFG_PATH.is_file():
        return {}
    return yaml.safe_load(CFG_PATH.read_text(encoding="utf-8")) or {}


def resolve_csv(cfg: dict[str, Any], year: int | None = None) -> Path | None:
    y = year or datetime.now(JST).year
    base = Path(cfg.get("csv_base_dir") or "").expanduser()
    path = base / f"{y}年度" / f"Zaim.{y}年度.csv"
    if path.is_file():
        return path
    prev = base / f"{y - 1}年度" / f"Zaim.{y - 1}年度.csv"
    return prev if prev.is_file() else None


def empty_rules(auto_min: int = AUTO_MIN_DEFAULT) -> dict[str, Any]:
    return {"updated_at": None, "auto_min_count": auto_min, "rules": {}}


def load_rules() -> dict[str, Any]:
    if RULES_PATH.is_file():
        try:
            data = json.loads(RULES_PATH.read_text(encoding="utf-8"))
            if isinstance(data, dict) and isinstance(data.get("rules"), dict):
                data.setdefault("auto_min_count", AUTO_MIN_DEFAULT)
                return data
        except Exception:
            pass
    return empty_rules()


def save_rules(data: dict[str, Any]) -> None:
    RULES_PATH.parent.mkdir(parents=True, exist_ok=True)
    data["updated_at"] = now_iso()
    RULES_PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def load_snapshot() -> dict[str, Any]:
    if SNAPSHOT_PATH.is_file():
        try:
            return json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"updated_at": None, "batch_id": None, "rows": []}


def save_snapshot(data: dict[str, Any]) -> None:
    SNAPSHOT_PATH.parent.mkdir(parents=True, exist_ok=True)
    data["updated_at"] = now_iso()
    SNAPSHOT_PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def auto_min(rules: dict[str, Any] | None = None) -> int:
    r = rules or load_rules()
    try:
        return max(2, int(r.get("auto_min_count") or AUTO_MIN_DEFAULT))
    except (TypeError, ValueError):
        return AUTO_MIN_DEFAULT


def can_auto(rule: dict[str, Any] | None, *, min_count: int | None = None) -> bool:
    if not rule:
        return False
    if rule.get("suppressed"):
        return False
    if rule.get("conflict"):
        return False
    n = min_count if min_count is not None else auto_min()
    try:
        return int(rule.get("count") or 0) >= n
    except (TypeError, ValueError):
        return False


def upsert_rule(
    rules: dict[str, Any],
    key: str,
    category: str,
    *,
    genre: str = "",
    source: str = "user_csv_diff",
    last_from: str = "",
) -> dict[str, Any]:
    """同一キーへカテゴリを記録。衝突したら count をリセットして conflict。"""
    cat = (category or "").strip()
    gen = (genre or "").strip()
    if not key or not cat:
        return {}
    store = rules.setdefault("rules", {})
    cur = dict(store.get(key) or {})
    if cur.get("suppressed"):
        return cur
    if cur.get("category") == cat:
        cur["count"] = int(cur.get("count") or 0) + 1
        cur["conflict"] = False
        if gen:
            cur["genre"] = gen
    else:
        prev_count = int(cur.get("count") or 0)
        if prev_count >= auto_min(rules) and cur.get("category"):
            cur["conflict"] = True
            cur["conflict_category"] = cat
            cur["count"] = 1
            cur["category"] = cat
            cur["genre"] = gen
        else:
            cur["category"] = cat
            cur["genre"] = gen
            cur["count"] = 1
            cur["conflict"] = False
    cur["source"] = source
    cur["last_from"] = last_from or now_iso()[:10]
    cur["updated_at"] = now_iso()
    store[key] = cur
    return cur


def suppress_key(rules: dict[str, Any], key: str, *, reason: str = "disputed") -> None:
    if not key:
        return
    store = rules.setdefault("rules", {})
    cur = dict(store.get(key) or {})
    cur["suppressed"] = True
    cur["suppress_reason"] = reason
    cur["updated_at"] = now_iso()
    store[key] = cur


def apply_disputed_suppressions(rules: dict[str, Any]) -> int:
    if not CHANGELOG_PATH.is_file():
        return 0
    try:
        cl = json.loads(CHANGELOG_PATH.read_text(encoding="utf-8"))
    except Exception:
        return 0
    n = 0
    for e in cl.get("entries") or []:
        if e.get("status") != "disputed":
            continue
        kind = str(e.get("kind") or e.get("target") or "")
        if kind not in ("set_category", "category", "category_review"):
            if e.get("action") not in ("set_category", "category_review"):
                continue
        key = str(e.get("learn_key") or learn_key(str(e.get("shop") or ""), str(e.get("item") or "")))
        if not key:
            continue
        before = (rules.get("rules") or {}).get(key) or {}
        if before.get("suppressed"):
            continue
        suppress_key(rules, key, reason="disputed")
        n += 1
    return n


def suspicious_substrings(cfg: dict[str, Any] | None = None) -> list[str]:
    cr = (cfg or load_cfg()).get("category_review") or {}
    return list(cr.get("suspicious_substrings") or ["その他", "使途不明", "未分類"])


def is_suspicious(cat: str, suspicious: list[str]) -> bool:
    c = cat or ""
    if not c:
        return False
    return any(s in c for s in suspicious)


def suggest_from_yaml(shop: str, item: str, yaml_rules: list[dict[str, Any]]) -> str | None:
    blob = f"{shop or ''}{item or ''}"
    for rule in yaml_rules or []:
        suggest = str(rule.get("suggest") or "").strip()
        if not suggest:
            continue
        for kw in rule.get("keywords") or []:
            if kw and kw in blob:
                return suggest
    return None


def resolve_suggestion(
    shop: str,
    item: str,
    *,
    yaml_rules: list[dict[str, Any]] | None = None,
    rules: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """学習ルール優先。count>=2 なら high、それ以外の提案は low。"""
    data = rules if rules is not None else load_rules()
    key = learn_key(shop, item)
    learned = (data.get("rules") or {}).get(key) if key else None
    yaml_suggest = suggest_from_yaml(shop, item, yaml_rules or [])
    out: dict[str, Any] = {
        "learn_key": key,
        "suggest": None,
        "genre": "",
        "confidence": "low",
        "source": None,
        "count": 0,
    }
    if learned and not learned.get("suppressed") and learned.get("category"):
        out["suggest"] = learned.get("category")
        out["genre"] = str(learned.get("genre") or "")
        out["source"] = "learn"
        out["count"] = int(learned.get("count") or 0)
        out["confidence"] = "high" if can_auto(learned, min_count=auto_min(data)) else "low"
        return out
    if yaml_suggest:
        out["suggest"] = yaml_suggest
        out["source"] = "yaml"
        out["confidence"] = "low"
    return out


def index_csv_rows(payments: list[dict[str, str]]) -> dict[str, dict[str, str]]:
    by_key: dict[str, dict[str, str]] = {}
    for r in payments:
        if (r.get("方法") or "") != "payment":
            continue
        try:
            if float(r.get("振替") or 0) != 0:
                continue
        except ValueError:
            pass
        if (r.get("残高調整") or "").strip() not in ("", "0", "0.0"):
            try:
                if float(r.get("残高調整") or 0) != 0:
                    continue
            except ValueError:
                pass
        if yen_of(r) <= 0:
            continue
        by_key[row_key(r)] = r
    return by_key


def learn_from_snapshot(
    snapshot: dict[str, Any],
    csv_index: dict[str, dict[str, str]],
    rules: dict[str, Any],
    suspicious: list[str],
) -> list[dict[str, Any]]:
    """スナップショット時点の自動後カテゴリと、今回 CSV が違えば手動修正として学習。"""
    learned: list[dict[str, Any]] = []
    for row in snapshot.get("rows") or []:
        rk = str(row.get("row_key") or "")
        cur = csv_index.get(rk)
        if not cur:
            continue
        csv_cat = (cur.get("カテゴリ") or "").strip()
        csv_gen = (cur.get("カテゴリの内訳") or "").strip()
        if not csv_cat or is_suspicious(csv_cat, suspicious):
            continue
        baseline = str(
            row.get("category_after_auto")
            or row.get("category_before")
            or ""
        ).strip()
        if csv_cat == baseline:
            continue
        key = str(row.get("learn_key") or learn_key(row.get("shop") or "", row.get("item") or ""))
        if not key:
            continue
        upsert_rule(
            rules,
            key,
            csv_cat,
            genre=csv_gen,
            source="user_csv_diff",
            last_from=str(row.get("date") or "")[:10],
        )
        learned.append(
            {
                "learn_key": key,
                "row_key": rk,
                "from": baseline,
                "to": csv_cat,
                "genre": csv_gen,
                "shop": row.get("shop"),
            }
        )
    return learned


def bootstrap_from_csv(
    payments: list[dict[str, str]],
    rules: dict[str, Any],
    suspicious: list[str],
) -> int:
    """店ごとに非・その他カテゴリが2件以上で優勢なら seed（既存ルールは潰さない）。"""
    by_key: dict[str, Counter[str]] = defaultdict(Counter)
    genre_of: dict[tuple[str, str], Counter[str]] = defaultdict(Counter)
    for r in payments:
        if (r.get("方法") or "") != "payment":
            continue
        if yen_of(r) <= 0:
            continue
        cat = (r.get("カテゴリ") or "").strip()
        if is_suspicious(cat, suspicious):
            continue
        key = learn_key(r.get("お店") or "", r.get("品目") or "")
        if not key:
            continue
        by_key[key][cat] += 1
        gen = (r.get("カテゴリの内訳") or "").strip()
        if gen:
            genre_of[(key, cat)][gen] += 1
    added = 0
    store = rules.setdefault("rules", {})
    min_n = auto_min(rules)
    for key, counts in by_key.items():
        if key in store:
            continue
        cat, n = counts.most_common(1)[0]
        total = sum(counts.values())
        if n < min_n:
            continue
        if n * 2 < total:
            continue
        gen = ""
        gcounts = genre_of.get((key, cat))
        if gcounts:
            gen = gcounts.most_common(1)[0][0]
        store[key] = {
            "category": cat,
            "genre": gen,
            "count": n,
            "conflict": False,
            "suppressed": False,
            "source": "bootstrap",
            "last_from": "csv",
            "updated_at": now_iso(),
        }
        added += 1
    return added


def snapshot_from_reviews(
    reviews: list[dict[str, Any]],
    *,
    applied_ok: set[str] | None = None,
    batch_id: str = "",
    csv_path: str = "",
) -> dict[str, Any]:
    applied_ok = applied_ok or set()
    rows: list[dict[str, Any]] = []
    for c in reviews:
        rk = str(c.get("row_key") or row_key(c))
        before = str(c.get("category") or "")
        suggest = str(c.get("suggest") or "")
        applied = rk in applied_ok or bool(c.get("auto_applied"))
        after = suggest if applied and suggest else before
        rows.append(
            {
                "row_key": rk,
                "date": c.get("date"),
                "amount": c.get("amount"),
                "shop": c.get("shop"),
                "item": c.get("item"),
                "pay": c.get("pay"),
                "method": c.get("method") or "payment",
                "learn_key": c.get("learn_key") or learn_key(c.get("shop") or "", c.get("item") or ""),
                "category_before": before,
                "genre_before": c.get("genre") or "",
                "category_after_auto": after,
                "genre_after_auto": c.get("suggest_genre") or c.get("genre") or "",
                "auto_applied": applied,
                "suggest": suggest or None,
                "confidence": c.get("confidence") or "low",
                "batch_id": batch_id,
            }
        )
    return {
        "batch_id": batch_id,
        "csv": csv_path,
        "rows": rows,
    }


def run(*, dry_run: bool = False, year: int | None = None) -> dict[str, Any]:
    cfg = load_cfg()
    rules = load_rules()
    cr = cfg.get("category_review") or {}
    if cr.get("auto_min_count"):
        try:
            rules["auto_min_count"] = max(2, int(cr["auto_min_count"]))
        except (TypeError, ValueError):
            pass
    csv_path = resolve_csv(cfg, year)
    suspicious = suspicious_substrings(cfg)
    suppressed_n = apply_disputed_suppressions(rules)
    snapshot = load_snapshot()
    payments: list[dict[str, str]] = []
    if csv_path and csv_path.is_file():
        payments = [
            r
            for r in csv.DictReader(csv_path.open(encoding="utf-8-sig"))
            if r.get("方法") == "payment"
        ]
    csv_index = index_csv_rows(payments)
    diffs = learn_from_snapshot(snapshot, csv_index, rules, suspicious)
    boot_n = bootstrap_from_csv(payments, rules, suspicious)
    ready = [
        {"key": k, **v}
        for k, v in (rules.get("rules") or {}).items()
        if can_auto(v, min_count=auto_min(rules))
    ]
    report = {
        "updated_at": now_iso(),
        "csv": str(csv_path) if csv_path else None,
        "snapshot_rows": len(snapshot.get("rows") or []),
        "learned_n": len(diffs),
        "bootstrap_n": boot_n,
        "suppressed_n": suppressed_n,
        "ready_auto_n": len(ready),
        "rule_count": len(rules.get("rules") or {}),
        "examples": diffs[:8],
        "ready_examples": [
            {
                "key": r["key"],
                "category": r.get("category"),
                "count": r.get("count"),
                "source": r.get("source"),
            }
            for r in ready[:8]
        ],
        "dry_run": dry_run,
    }
    if not dry_run:
        save_rules(rules)
        LAST_PATH.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    return report


def _self_test() -> int:
    rules = empty_rules(2)
    upsert_rule(rules, "アオキ", "β.2C.食費", source="user_csv_diff", last_from="2026-08-01")
    r1 = resolve_suggestion("アオキ", "", yaml_rules=[], rules=rules)
    assert r1["suggest"] == "β.2C.食費"
    assert r1["confidence"] == "low"
    assert r1["count"] == 1
    upsert_rule(rules, "アオキ", "β.2C.食費", source="user_csv_diff", last_from="2026-08-08")
    r2 = resolve_suggestion("アオキ", "", yaml_rules=[], rules=rules)
    assert r2["confidence"] == "high", r2
    assert can_auto((rules["rules"]["アオキ"]))
    upsert_rule(rules, "アオキ", "β.5C.日用雑貨", source="user_csv_diff", last_from="2026-08-15")
    r3 = resolve_suggestion("アオキ", "", yaml_rules=[], rules=rules)
    assert r3["confidence"] == "low"
    assert rules["rules"]["アオキ"]["conflict"] is True
    yaml_rules = [{"suggest": "β.2C.食費", "keywords": ["アオキ"]}]
    empty = empty_rules()
    r4 = resolve_suggestion("アオキ", "", yaml_rules=yaml_rules, rules=empty)
    assert r4["source"] == "yaml" and r4["confidence"] == "low"
    snap = {
        "rows": [
            {
                "row_key": "2026-08-10|500|ダイソー|Olive|payment",
                "shop": "ダイソー",
                "item": "",
                "date": "2026-08-10",
                "category_before": "β.12.C.その他/使途不明",
                "category_after_auto": "β.12.C.その他/使途不明",
                "learn_key": shop_key("ダイソー"),
            }
        ]
    }
    csv_row = {
        "日付": "2026-08-10",
        "支出": "500",
        "お店": "ダイソー",
        "支払元": "Olive",
        "方法": "payment",
        "カテゴリ": "β.5C.日用雑貨",
        "カテゴリの内訳": "",
        "振替": "0",
        "残高調整": "",
    }
    learned = learn_from_snapshot(
        snap, {row_key(csv_row): csv_row}, empty_rules(), ["その他", "使途不明"]
    )
    assert len(learned) == 1
    print("# self-test ok")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--year", type=int, default=None)
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args(argv)
    if args.self_test:
        return _self_test()
    report = run(dry_run=args.dry_run, year=args.year)
    print(
        f"# zaim learn learned={report['learned_n']} bootstrap={report['bootstrap_n']} "
        f"ready_auto={report['ready_auto_n']} rules={report['rule_count']}",
        file=sys.stderr,
    )
    if args.json or args.dry_run:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(
            f"📎 Zaim費目学習 差分{report['learned_n']} "
            f"bootstrap{report['bootstrap_n']} 次回自動可{report['ready_auto_n']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
