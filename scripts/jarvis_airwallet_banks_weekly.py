#!/usr/bin/env python3
"""エアウォレット対応銀行の週次調査。

公式 FAQ は SPA で HTTP 直取得できないため:
  1) config の baseline_official_banks（FAQ 記載時点）を正本シード
  2) Tavily 検索で「対応銀行の追加」ニュース／FAQ 更新を検知
  3) 家計銀行が新たに対応候補になったら attention

  cd ~/git-repos && set -a && source .env.jarvis_private && set +a
  ~/selenium_env/venv/bin/python scripts/jarvis_airwallet_banks_weekly.py
  ~/selenium_env/venv/bin/python scripts/jarvis_airwallet_banks_weekly.py --dry-run
  ~/selenium_env/venv/bin/python scripts/jarvis_airwallet_banks_weekly.py --json
  ~/selenium_env/venv/bin/python scripts/jarvis_airwallet_banks_weekly.py --mark-supported tokairokin
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import yaml

JST = ZoneInfo("Asia/Tokyo")
REPO = Path(__file__).resolve().parents[1]
CONFIG = REPO / "config" / "kurashift_airwallet_banks.yaml"
STATE = REPO / ".jarvis_state" / "airwallet_banks_weekly.json"
DEFAULT_URL = "https://faq.coinplus.jp/s/article/000031794"


def now_iso() -> str:
    return datetime.now(JST).strftime("%Y-%m-%dT%H:%M:%S%z")


def load_config() -> dict[str, Any]:
    if not CONFIG.is_file():
        return {}
    return yaml.safe_load(CONFIG.read_text(encoding="utf-8")) or {}


def load_state() -> dict[str, Any]:
    if not STATE.is_file():
        return {}
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def save_state(data: dict[str, Any]) -> None:
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def normalize_bank(name: str) -> str:
    s = (name or "").strip()
    s = s.replace("三菱UFJ銀行", "三菱ＵＦＪ銀行")
    s = re.sub(r"\s+", "", s)
    return s


def bank_on_list(match_names: list[str], official: list[str]) -> bool:
    norms = {normalize_bank(x) for x in official}
    for m in match_names or []:
        nm = normalize_bank(m)
        if nm in norms:
            return True
        if any(nm in o or o in nm for o in norms):
            return True
    return False


def tavily_search(query: str) -> dict[str, Any]:
    key = (os.environ.get("TAVILY_API_KEY") or "").strip()
    if not key:
        raise RuntimeError("TAVILY_API_KEY 未設定")
    body = json.dumps(
        {
            "api_key": key,
            "query": query,
            "search_depth": "advanced",
            "max_results": 8,
            "include_answer": True,
            "time_range": "month",
        },
        ensure_ascii=False,
    ).encode("utf-8")
    req = urllib.request.Request(
        "https://api.tavily.com/search",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))


def harvest_mentioned_banks(
    text: str, candidates: list[tuple[str, str, list[str]]]
) -> list[dict[str, str]]:
    """candidates: (id, label, match_names)。誤検知防止のため正式名の完全一致のみ。"""
    hits: list[dict[str, str]] = []
    blob = text or ""
    # 対応追加の文脈が近いときだけ拾う
    if not any(k in blob for k in ("登録できる金融機関", "対応銀行", "対応金融機関", "金融機関口座")):
        return hits
    for hid, label, matches in candidates:
        for m in matches:
            if m and m in blob:
                hits.append({"id": hid, "label": label, "matched": m})
                break
    return hits


def mark_supported(bank_id: str, *, dry_run: bool) -> int:
    """手動で AW 確認済みを state に追記（YAML は別途更新推奨）。"""
    prev = load_state()
    confirmed = list(prev.get("manual_confirmed_ids") or [])
    if bank_id not in confirmed:
        confirmed.append(bank_id)
    prev["manual_confirmed_ids"] = confirmed
    prev["updated_at"] = now_iso()
    prev["summary"] = f"手動確認: {bank_id} を AW 利用可にマーク"
    prev["level"] = "ok"
    if not dry_run:
        save_state(prev)
    print(f"✅ mark-supported: {bank_id}")
    return 0


def run(*, dry_run: bool, as_json: bool, skip_tavily: bool) -> dict[str, Any]:
    cfg = load_config()
    policy = cfg.get("policy") or {}
    notify = cfg.get("notify") or {}
    url = str(policy.get("official_list_url") or DEFAULT_URL)
    baseline = list(policy.get("baseline_official_banks") or [])
    prev = load_state()
    manual_confirmed = set(prev.get("manual_confirmed_ids") or [])

    # 公式一覧: 前回成功があればそれ、なければ baseline
    official = list(prev.get("official_banks") or []) or list(baseline)
    source = "prev" if prev.get("official_banks") else "baseline"
    if not official and baseline:
        official = list(baseline)
        source = "baseline"

    prev_set = {normalize_bank(x) for x in (prev.get("official_banks") or [])}
    # 初回: baseline を seed（added 扱いにしない）
    first_seed = not bool(prev.get("official_banks")) and bool(baseline)

    tavily_err: str | None = None
    tavily_snippets: list[str] = []
    news_hits: list[dict[str, str]] = []
    as_of_hint = str(policy.get("list_as_of_hint") or "")

    household = cfg.get("household_banks") or []
    watch_candidates: list[tuple[str, str, list[str]]] = []
    for row in household:
        if not isinstance(row, dict):
            continue
        status = str(row.get("aw_status") or "watch")
        if status in ("blocked_other_owner", "confirmed", "likely"):
            continue
        watch_candidates.append(
            (
                str(row.get("id") or ""),
                str(row.get("label") or ""),
                list(row.get("match_names") or []),
            )
        )

    if not skip_tavily:
        try:
            queries = [
                "エアウォレット OR COIN+ 登録できる金融機関 一覧",
                "エアウォレット 対応銀行 追加 OR 新規",
                "faq.coinplus.jp 登録できる金融機関",
            ]
            blob_parts: list[str] = []
            for q in queries:
                data = tavily_search(q)
                ans = (data.get("answer") or "").strip()
                if ans:
                    blob_parts.append(ans)
                for r in data.get("results") or []:
                    title = (r.get("title") or "").strip()
                    content = (r.get("content") or "").strip()
                    blob_parts.append(f"{title}\n{content}")
                    tavily_snippets.append(f"{title}: {content[:160]}")
            blob = "\n".join(blob_parts)
            news_hits = harvest_mentioned_banks(blob, watch_candidates)
            # FAQ 本文の「※YYYY年M月D日時点」だけ採用
            m = re.search(r"※\s*(20\d{2}年\d{1,2}月\d{1,2}日時点)", blob)
            if m:
                as_of_hint = m.group(1)
        except (RuntimeError, urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as e:
            tavily_err = str(e)[:200]

    newly_supported: list[dict[str, str]] = []
    # news で not_on_list / watch が言及されたら候補
    seen_new: set[str] = set()
    for h in news_hits:
        hid = h["id"]
        if hid in seen_new:
            continue
        # すでに一覧にあるなら「新規対応」ではない
        row = next((x for x in household if isinstance(x, dict) and x.get("id") == hid), None)
        matches = list((row or {}).get("match_names") or [])
        if bank_on_list(matches, official):
            continue
        seen_new.add(hid)
        newly_supported.append({"id": hid, "label": h["label"], "via": "tavily"})

    # 前回一覧との差分（手動で official_banks を増やしたとき）
    added = [b for b in official if normalize_bank(b) not in prev_set] if prev_set and not first_seed else []
    removed = [
        b
        for b in (prev.get("official_banks") or [])
        if normalize_bank(b) not in {normalize_bank(x) for x in official}
    ]

    # household が baseline に載っていて aw_status=not_on_list なら設定ミス注意
    config_mismatch: list[str] = []
    household_support: dict[str, Any] = {}
    confirmed: list[str] = []
    blocked: list[str] = []
    still_missing: list[str] = []

    for row in household:
        if not isinstance(row, dict):
            continue
        hid = str(row.get("id") or "")
        label = str(row.get("label") or hid)
        matches = list(row.get("match_names") or [])
        on = bank_on_list(matches, official)
        status = str(row.get("aw_status") or "watch")
        if hid in manual_confirmed:
            status = "confirmed"
        household_support[hid] = {
            "label": label,
            "on_official_list": on,
            "aw_status": status,
            "prefer_aw_under_100k": bool(row.get("prefer_aw_under_100k")),
            "owner": row.get("owner"),
        }
        if status == "blocked_other_owner":
            blocked.append(label)
            continue
        if status in ("confirmed", "likely") or (on and status != "not_on_list"):
            confirmed.append(label)
        if status == "not_on_list":
            if on:
                config_mismatch.append(label)
            else:
                still_missing.append(label)
        elif not on and status == "watch":
            still_missing.append(label)

    # baseline 上は対応済みだが YAML が not_on_list のまま → お知らせ
    for label in config_mismatch:
        hid = next(
            (
                str(x.get("id"))
                for x in household
                if isinstance(x, dict) and x.get("label") == label
            ),
            "",
        )
        if hid and not any(x.get("id") == hid for x in newly_supported):
            newly_supported.append({"id": hid, "label": label, "via": "baseline_mismatch"})

    level = "ok"
    summary_parts: list[str] = []
    detail_parts: list[str] = []
    max_aw = int(policy.get("prefer_airwallet_max_jpy") or 100_000)

    if newly_supported and notify.get("household_became_supported", True):
        level = "attention"
        labels = "、".join(x["label"] for x in newly_supported)
        summary_parts.append(f"家計銀行が新たに対応の可能性: {labels}")
        detail_parts.append(
            "アプリの口座設定で紐づけできるか確認し、10万以下の寄せは AW を優先してよい。"
        )

    if added and notify.get("official_list_grew", True):
        if level == "ok":
            level = "info"
        summary_parts.append(f"公式一覧に新規 {len(added)} 行")
        detail_parts.append("新規: " + "、".join(added[:12]))

    if removed:
        if level == "ok":
            level = "info"
        summary_parts.append(f"公式一覧から削除 {len(removed)}")

    if tavily_err:
        if level == "ok":
            level = "info"
        summary_parts.append(f"Tavily: {tavily_err[:80]}")

    if not summary_parts:
        summary_parts.append(
            f"変化なし · 公式シード {len(official)} 行（{as_of_hint or source}）"
            f" · ≤{max_aw:,}円は AW 優先（紐づけ可のみ）"
        )

    detail_parts.append(
        f"方針: {max_aw:,}円以下かつ同一名義・紐づけ済みならエアウォレット優先。"
        " OTP/最終確認があるなら IB 自動化より AW の方が早いことが多い。"
    )
    if confirmed:
        detail_parts.append("AW 利用可（確認済/想定）: " + "、".join(confirmed))
    if blocked:
        detail_parts.append("AW 不可（名義違い等）: " + "、".join(blocked))
    if still_missing:
        detail_parts.append("一覧外・要監視: " + "、".join(still_missing))
    detail_parts.append(f"出典シード: {url}（{as_of_hint or 'as_of unknown'} / source={source}）")
    if tavily_snippets:
        detail_parts.append("週次Web抜粋:\n" + "\n".join(f"- {s}" for s in tavily_snippets[:5]))

    out: dict[str, Any] = {
        "updated_at": now_iso(),
        "level": level,
        "summary": " · ".join(summary_parts),
        "detail": "\n".join(detail_parts),
        "official_banks": official,
        "official_count": len(official),
        "official_url": url,
        "official_source": source,
        "list_as_of": as_of_hint,
        "added": added,
        "removed": removed,
        "newly_supported_household": newly_supported,
        "household_support": household_support,
        "manual_confirmed_ids": sorted(manual_confirmed),
        "prefer_airwallet_max_jpy": max_aw,
        "tavily_error": tavily_err,
        "last_success_at": now_iso(),
        "href": "/money-ops",
    }

    stale_days = int(notify.get("stale_days") or 10)
    if out.get("last_success_at"):
        try:
            ts = datetime.strptime(
                re.sub(r"([+-]\d{2}):(\d{2})$", r"\1\2", str(out["last_success_at"])[:22]),
                "%Y-%m-%dT%H:%M:%S%z",
            )
            age = (datetime.now(JST) - ts.astimezone(JST)).days
            out["days_since_success"] = age
            if age >= stale_days and level == "ok":
                out["level"] = "info"
                out["summary"] = f"最終成功から{age}日 · " + out["summary"]
        except Exception:
            pass

    if not dry_run:
        save_state(out)

    if as_json:
        print(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        print("📎 エアウォレット対応銀行（週次）")
        print(f"- 判定: {out['level']}")
        print(f"- {out['summary']}")
        if newly_supported:
            print("- 新規候補（家計）: " + "、".join(x["label"] for x in newly_supported))
        print(f"- 公式件数: {len(official)}（{source} / {as_of_hint or '—'}）")
        print(f"- 方針: ≤{max_aw:,}円かつ紐づけ可 → AW 優先")
        if dry_run:
            print("- （dry-run: state 未保存）")
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="AirWallet bank list weekly check")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--skip-tavily", action="store_true")
    ap.add_argument("--mark-supported", metavar="BANK_ID", help="手動で AW 可にマーク")
    args = ap.parse_args()
    if args.mark_supported:
        return mark_supported(args.mark_supported, dry_run=args.dry_run)
    run(dry_run=args.dry_run, as_json=args.json, skip_tavily=args.skip_tavily)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
