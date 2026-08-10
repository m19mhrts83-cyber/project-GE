#!/usr/bin/env python3
"""携帯プラン乗り換えウォッチ → .jarvis_state/mobile_plan.json

Zaim 実績と config/mobile_plan_watch.yaml を突き合わせ、
オプション解約漏れ・キャッシュバック未受取・次回乗り換えリマインドを判定する。

例:
  python scripts/jarvis_mobile_plan_check.py
  python scripts/jarvis_mobile_plan_check.py --mark-checked
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
import unicodedata
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

try:
    import yaml
except ImportError:
    print("PyYAML required", file=sys.stderr)
    raise SystemExit(1)

ROOT = Path(__file__).resolve().parents[1]
CFG_PATH = ROOT / "config" / "mobile_plan_watch.yaml"
STATE_PATH = ROOT / ".jarvis_state" / "mobile_plan.json"
ENV_PATH = ROOT / ".env.jarvis_private"
JST = ZoneInfo("Asia/Tokyo")

LEVEL_RANK = {"ok": 0, "info": 1, "warn": 2, "attention": 3}


def load_env() -> None:
    if not ENV_PATH.exists():
        return
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def today_jst() -> date:
    return datetime.now(JST).date()


def load_cfg() -> dict[str, Any]:
    return yaml.safe_load(CFG_PATH.read_text(encoding="utf-8")) or {}


def load_state() -> dict[str, Any]:
    if not STATE_PATH.exists():
        return {"version": 1, "disabled": False}
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"version": 1, "disabled": False}


def save_state(data: dict[str, Any]) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def nf(s: str) -> str:
    s = unicodedata.normalize("NFKC", (s or "").strip())
    return re.sub(r"\s+", "", s).lower()


def parse_yen(r: dict[str, str]) -> float:
    try:
        return float(r.get("支出") or 0) or 0.0
    except ValueError:
        return 0.0


def resolve_csv(cfg: dict[str, Any], year: int) -> Path:
    z = cfg.get("zaim") or {}
    base = Path(z.get("csv_base_dir") or "").expanduser()
    return base / f"{year}年度" / f"Zaim.{year}年度.csv"


def shop_blob(r: dict[str, str]) -> str:
    return " ".join(
        [
            r.get("お店") or "",
            r.get("品目") or "",
            r.get("メモ") or "",
            r.get("カテゴリの内訳") or "",
        ]
    )


def match_keywords(blob: str, keywords: list[str]) -> bool:
    n = nf(blob)
    return any(nf(k) in n for k in keywords if k)


def load_mobile_rows(cfg: dict[str, Any], today: date) -> list[dict[str, Any]]:
    z = cfg.get("zaim") or {}
    kws = list(z.get("shop_keywords") or []) + list(z.get("include_air_keywords") or [])
    years = {today.year, today.year - 1}
    out: list[dict[str, Any]] = []
    for y in sorted(years):
        path = resolve_csv(cfg, y)
        if not path.is_file():
            continue
        rows = list(csv.DictReader(path.open(encoding="utf-8-sig")))
        for r in rows:
            yen = parse_yen(r)
            if yen <= 0:
                continue
            blob = shop_blob(r)
            if not match_keywords(blob, kws):
                continue
            d = (r.get("日付") or "").strip()
            if len(d) < 7:
                continue
            out.append(
                {
                    "date": d,
                    "month": d[:7],
                    "yen": yen,
                    "shop": (r.get("お店") or "").strip(),
                    "pay_from": (r.get("支払元") or "").strip()[:40],
                    "category": (r.get("カテゴリの内訳") or r.get("カテゴリ") or "").strip(),
                }
            )
    out.sort(key=lambda x: x["date"])
    return out


def monthly_totals(rows: list[dict[str, Any]]) -> dict[str, float]:
    m: dict[str, float] = defaultdict(float)
    for r in rows:
        m[r["month"]] += r["yen"]
    return dict(sorted(m.items()))


def pick_latest_compare_month(
    months: dict[str, float],
    skip: set[str],
    today: date,
    from_month: str | None = None,
) -> str | None:
    """当月以外・skip 以外・契約月より後の最新月を比較対象にする。

    from_month（契約月）以前は旧キャリア分として除外する。
    """
    cur = today.strftime("%Y-%m")
    cands = []
    for m in months:
        if m == cur or m in skip:
            continue
        if from_month and m <= from_month:
            continue
        cands.append(m)
    return cands[-1] if cands else None


def bump(level: str, new: str) -> str:
    if LEVEL_RANK.get(new, 0) > LEVEL_RANK.get(level, 0):
        return new
    return level


def check_credentials(cfg: dict[str, Any]) -> list[str]:
    missing: list[str] = []
    lines = (cfg.get("current_contract") or {}).get("lines") or []
    for ln in lines:
        for key in ("env_phone", "env_password"):
            var = ln.get(key) or ""
            if not var:
                continue
            if not (os.environ.get(var) or "").strip():
                missing.append(var)
    for opt in cfg.get("options") or []:
        for key in ("env_login", "env_password"):
            var = opt.get(key) or ""
            if var and not (os.environ.get(var) or "").strip():
                missing.append(var)
    # unique preserve order
    seen: set[str] = set()
    uniq: list[str] = []
    for m in missing:
        if m not in seen:
            seen.add(m)
            uniq.append(m)
    return uniq


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mark-checked", action="store_true")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    load_env()
    if (os.environ.get("JARVIS_MOBILE_PLAN_DISABLE") or "").strip() == "1":
        print("")
        return 0

    state = load_state()
    if state.get("disabled"):
        print("")
        return 0

    if not CFG_PATH.is_file():
        print("config/mobile_plan_watch.yaml がありません", file=sys.stderr)
        return 1

    cfg = load_cfg()
    today = today_jst()
    level = "ok"
    detail_lines: list[str] = []
    issues: list[str] = []

    # --- next switch reminder ---
    ns = cfg.get("next_switch") or {}
    switch_s = str(ns.get("date") or "")
    switch_to = str(ns.get("to") or "次キャリア")
    days_to_switch: int | None = None
    pin_top = False
    show_banner = False
    if switch_s:
        try:
            switch_d = date.fromisoformat(switch_s)
            days_to_switch = (switch_d - today).days
            info_d = int(ns.get("remind_days_info") or 60)
            warn_d = int(ns.get("remind_days_warn") or 30)
            att_d = int(ns.get("remind_days_attention") or 14)
            if days_to_switch < 0:
                issues.append(f"乗り換え予定日 {switch_s} を経過（{abs(days_to_switch)}日）")
                level = bump(level, "attention")
                pin_top = True
                show_banner = True
            elif days_to_switch <= att_d:
                issues.append(f"{switch_s} {switch_to} 移行まで残り{days_to_switch}日")
                level = bump(level, "attention")
                pin_top = True
                show_banner = True
            elif days_to_switch <= warn_d:
                issues.append(f"{switch_s} {switch_to} 移行まで残り{days_to_switch}日")
                level = bump(level, "warn")
                pin_top = True
                show_banner = True
            elif days_to_switch <= info_d:
                issues.append(f"{switch_s} {switch_to} 移行まで残り{days_to_switch}日（予告）")
                level = bump(level, "info")
                pin_top = True
                show_banner = True
        except ValueError:
            issues.append(f"next_switch.date 不正: {switch_s}")
            level = bump(level, "warn")

    specials = [
        str(s.get("text") or "")
        for s in (cfg.get("special_notes") or [])
        if s.get("open", True) and s.get("text")
    ]
    for t in specials:
        detail_lines.append(f"特記: {t}")

    # --- options ---
    open_opts: list[dict[str, Any]] = []
    for opt in cfg.get("options") or []:
        if opt.get("canceled_at"):
            continue
        cancel_by = opt.get("cancel_by")
        overdue = False
        if cancel_by:
            try:
                overdue = today > date.fromisoformat(str(cancel_by))
            except ValueError:
                overdue = False
        open_opts.append({**opt, "overdue": overdue})
        if overdue:
            issues.append(
                f"オプション未解約疑い: {opt.get('name')}（〜{cancel_by} / {opt.get('cancel_via') or '—'}）"
            )
            level = bump(level, "warn")

    # --- cashback ---
    for cb in cfg.get("cashback") or []:
        if cb.get("received_at"):
            continue
        due = cb.get("due")
        if not due:
            continue
        try:
            due_d = date.fromisoformat(str(due))
        except ValueError:
            continue
        if today > due_d:
            issues.append(
                f"キャッシュバック未受取: {cb.get('label')} {int(cb.get('yen') or 0):,}円（期限 {due}）"
            )
            level = bump(level, "warn")
        elif today >= due_d - timedelta(days=14):
            issues.append(
                f"キャッシュバック受取時期: {cb.get('label')} {int(cb.get('yen') or 0):,}円（due {due}）"
            )
            level = bump(level, "info")

    # --- credentials ---
    missing_creds = check_credentials(cfg)
    if missing_creds:
        issues.append(
            "認証情報未登録: "
            + ", ".join(missing_creds[:8])
            + ("…" if len(missing_creds) > 8 else "")
            + "（.env.jarvis_private へ追記）"
        )
        level = bump(level, "info")

    # --- Zaim ---
    rows = load_mobile_rows(cfg, today)
    months = monthly_totals(rows)
    skip = set(str(x) for x in (cfg.get("skip_months") or []))
    expected = int(cfg.get("expected_monthly_yen") or 0)
    over_thr = int(cfg.get("warn_over_yen") or 0)
    contracted = str((cfg.get("current_contract") or {}).get("contracted_at") or "")
    from_month = contracted[:7] if len(contracted) >= 7 else None
    compare_month = pick_latest_compare_month(months, skip, today, from_month)
    compare_yen = months.get(compare_month or "", 0.0)
    over_amount = 0.0
    if compare_month and expected > 0:
        limit = expected + over_thr
        if compare_yen > limit:
            over_amount = compare_yen - expected
            issues.append(
                f"{compare_month} 実績 {int(compare_yen):,}円 > 想定 {expected:,}円"
                f"（超過 {int(over_amount):,}円・解約漏れの可能性）"
            )
            level = bump(level, "warn")

    month_lines = [f"{m}: {int(v):,}円" for m, v in list(months.items())[-6:]]
    if month_lines:
        detail_lines.append("月次: " + " / ".join(month_lines))
    if compare_month:
        detail_lines.append(
            f"比較月: {compare_month} = {int(compare_yen):,}円（想定 {expected:,}±{over_thr:,}）"
        )
    if open_opts:
        names = ", ".join(str(o.get("name") or "") for o in open_opts[:6])
        detail_lines.append(f"未消し込みオプション: {names}")
    if switch_s and days_to_switch is not None:
        detail_lines.insert(
            0,
            f"次回乗り換え: {switch_s} → {switch_to}（残り {days_to_switch} 日）",
        )

    # summary
    if days_to_switch is not None and pin_top:
        summary = f"{switch_s} {switch_to} 移行まで残り{days_to_switch}日"
        if specials:
            summary += "｜" + specials[0][:40]
    elif issues:
        summary = issues[0]
    elif compare_month:
        summary = f"{compare_month} 実績 {int(compare_yen):,}円（想定内）"
    else:
        summary = "携帯プラン監視中（Zaim 比較月なし）"

    cc = cfg.get("current_contract") or {}
    payload = {
        "version": 1,
        "disabled": False,
        "level": level,
        "summary": summary,
        "detail": "\n".join(detail_lines),
        "issues": issues,
        "carrier": cc.get("carrier"),
        "contracted_at": cc.get("contracted_at"),
        "next_switch_date": switch_s,
        "next_switch_to": switch_to,
        "days_to_switch": days_to_switch,
        "pin_top": pin_top,
        "show_banner": show_banner,
        "special_notes": specials,
        "expected_monthly_yen": expected,
        "compare_month": compare_month,
        "compare_yen": int(compare_yen) if compare_month else None,
        "over_yen": int(over_amount) if over_amount else 0,
        "monthly": {k: int(v) for k, v in months.items()},
        "open_options": [
            {
                "id": o.get("id"),
                "name": o.get("name"),
                "yen": o.get("yen"),
                "cancel_via": o.get("cancel_via"),
                "cancel_by": o.get("cancel_by"),
                "overdue": o.get("overdue"),
            }
            for o in open_opts
        ],
        "missing_credentials": missing_creds,
        "recent_rows": rows[-8:],
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }

    if args.mark_checked:
        state.update(payload)
        save_state(state)

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    print("📎 携帯プラン")
    print(f"- 判定: {level}")
    print(f"- {summary}")
    if switch_s:
        print(f"- 次回乗り換え: {switch_s} → {switch_to}（残り {days_to_switch} 日）")
    for t in specials:
        print(f"- 特記: {t}")
    if compare_month:
        print(
            f"- Zaim比較: {compare_month} {int(compare_yen):,}円"
            f"（想定 {expected:,}円 / 閾値+{over_thr:,}）"
        )
    if month_lines:
        print(f"- 月次推移: {' / '.join(month_lines)}")
    if open_opts:
        print(f"- 未消し込みオプション: {len(open_opts)}件")
        for o in open_opts[:5]:
            flag = "期限超過" if o.get("overdue") else "要確認"
            print(
                f"  · [{flag}] {o.get('name')} {o.get('yen')}円"
                f" — {o.get('cancel_via') or '—'}"
            )
    if missing_creds:
        print(f"- 認証未登録: {', '.join(missing_creds[:6])}")
    for iss in issues[:6]:
        if iss not in summary:
            print(f"- ⚠ {iss}")
    print("- 正本: config/mobile_plan_watch.yaml / .env.jarvis_private（YMOBILE_L*）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
