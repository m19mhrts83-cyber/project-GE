#!/usr/bin/env python3
"""
ETC 平日朝夕・還元額の自動取得（smile-etc）→ etc_monthly → ダッシュボード。

公式（NEXCO / smile-etc Q&A）:
  利用月（1日〜末日）の対象走行 → 翌月20日に還元額付与。

定例:
  launchd 毎月 20〜26日 09:30 JST（付与当日〜遅延吸収）。
  朝オープン取りこぼしも jarvis_morning_mac_refresh から拾う。

使い方:
  python scripts/jarvis_etc_rebate_fetch.py --dry-run
  python scripts/jarvis_etc_rebate_fetch.py --apply --push
  python scripts/jarvis_etc_rebate_fetch.py --target-month 2026-07 --apply --push --force
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

JST = ZoneInfo("Asia/Tokyo")
REPO = Path(__file__).resolve().parents[1]
STATE_PATH = REPO / ".jarvis_state" / "etc_monthly.json"
PRIVATE_ENV = REPO / ".env.jarvis_private"
LOGIN_URL = (
    "https://www2.smile-etc.jp/NASApp/etcmlg/MlgReq"
    "?gvlddpef=1013000000&mdwsetmb=1013000000"
)
REBATE_URL = (
    "https://www2.smile-etc.jp/NASApp/etcmlg/MlgReq"
    "?gvlddpef=1015000000&mdwsetmb=1015000000"
)
POINTS_URL = (
    "https://www2.smile-etc.jp/NASApp/etcmlg/MlgReq"
    "?gvlddpef=1014000000&mdwsetmb=1014000000&H_KBN=NEXCO"
)

# 付与日は翌月20日。表示遅れを見て 20〜26 を定例窓とする（既存ウィンドウBと整合）。
AUTO_WINDOW_DAYS = frozenset(range(20, 27))


def load_dotenv(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.is_file():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.+?)\s*$", line)
        if m and not line.lstrip().startswith("#"):
            out[m.group(1)] = m.group(2).strip().strip("\"'")
    return out


def load_state() -> dict[str, Any]:
    if STATE_PATH.is_file():
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    return {"disabled": False, "rebate_history": []}


def save_state(state: dict[str, Any]) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(
        json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def month_key(dt: datetime) -> str:
    return dt.strftime("%Y-%m")


def add_months(ym: str, delta: int) -> str:
    y, m = map(int, ym.split("-"))
    m += delta
    while m > 12:
        m -= 12
        y += 1
    while m < 1:
        m += 12
        y -= 1
    return f"{y}-{m:02d}"


def ym_label(ym: str) -> str:
    """smile-etc 画面は『2026年08月分』のように月がゼロ埋め。"""
    y, m = ym.split("-")
    return f"{y}年{int(m):02d}月"


def default_target_month(now: datetime) -> str | None:
    """定例窓（20〜26日）なら前月＝直前に付与された利用月。それ以外は None。"""
    if now.day not in AUTO_WINDOW_DAYS:
        return None
    return add_months(month_key(now), -1)


def history_has(state: dict[str, Any], target: str) -> bool:
    for h in state.get("rebate_history") or []:
        if isinstance(h, dict) and h.get("target_month") == target and h.get("rebate_yen") is not None:
            return True
    return False


def rate_from_trip_count(count: int | None) -> int | None:
    if count is None:
        return None
    if count <= 4:
        return 0
    if count <= 9:
        return 30
    return 50


def upsert_rebate_history(state: dict[str, Any], result: dict[str, Any]) -> None:
    target = result.get("target_month")
    if not target:
        return
    entry = {
        "target_month": target,
        "rebate_yen": result.get("rebate_yen"),
        "asayu_trip_count": result.get("asayu_trip_count"),
        "asayu_rate_pct": result.get("asayu_rate_pct"),
        "savings_yen": result.get("savings_yen"),
        "at": result.get("at"),
        "note": result.get("note") or "",
        "source": result.get("source") or "smile-etc_auto",
    }
    hist = [h for h in (state.get("rebate_history") or []) if isinstance(h, dict)]
    hist = [h for h in hist if h.get("target_month") != target]
    hist.append(entry)
    hist.sort(key=lambda h: str(h.get("target_month") or ""), reverse=True)
    state["rebate_history"] = hist[:24]


def parse_tokuten_yen(text: str) -> int | None:
    """還元額明細本文から『特典 … 平日朝夕』金額を取る。"""
    # 例: 特典 5,190 … [平日朝夕割引（ＮＥＸＣＯ）]
    m = re.search(
        r"特典\s*([0-9,]+).*?平日朝夕",
        text,
        flags=re.S,
    )
    if m:
        return int(m.group(1).replace(",", ""))
    m2 = re.search(r"平日朝夕割引[^0-9]{0,40}?([0-9,]+)\s*円", text)
    if m2:
        return int(m2.group(1).replace(",", ""))
    # 特典行のみ（平日朝夕表記が別セル）
    m3 = re.search(r"特典\s*([0-9,]+)", text)
    if m3 and "特典" in text:
        return int(m3.group(1).replace(",", ""))
    return None


def parse_opening_balance(text: str) -> int | None:
    """
    特典行が欠ける月のフォールバック。
    最初の『利用』行の（還元額利用絶対値 + 残高）＝付与直後の開始残高。
    """
    pairs = re.findall(r"-([0-9,]+)\s+([0-9,]+)\s+確定", text)
    if not pairs:
        return None
    first_use = int(pairs[0][0].replace(",", ""))
    first_bal = int(pairs[0][1].replace(",", ""))
    return first_use + first_bal


def parse_nexco_points_for_usage(text: str, usage_ym: str) -> int | None:
    """ポイント明細の『2026年07月分』行のプラスポイント。"""
    label = ym_label(usage_ym)
    # 例: 26/08/20  2026年07月分  2028/03  2,574    3,983
    m = re.search(
        rf"{re.escape(label)}分\s+(?:\d{{4}}/\d{{2}}\s+)?([0-9,]+)",
        text,
    )
    if m:
        return int(m.group(1).replace(",", ""))
    return None


def scrape_rebate(
    *,
    mileage_id: str,
    password: str,
    target_month: str,
    headless: bool = True,
) -> dict[str, Any]:
    """smile-etc から target_month（利用月）の還元額を取得。"""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as e:
        raise RuntimeError("playwright が必要です（selenium_env）") from e

    grant_month = add_months(target_month, 1)
    grant_label = ym_label(grant_month)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        page = browser.new_page(locale="ja-JP")
        page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=60000)
        page.fill("input[name=mlgloginid]", mileage_id)
        page.fill("input[name=mlgpassword]", password)
        page.click("input[type=submit]")
        page.wait_for_timeout(2500)

        page.goto(REBATE_URL, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(1200)

        found = False
        for _ in range(10):
            body = page.inner_text("body")
            m = re.search(r"(20\d{2}年\d{1,2}月)分", body)
            cur = m.group(1) if m else ""
            if cur == grant_label:
                found = True
                break
            prev = page.locator("a:has-text('前月')")
            if prev.count() == 0:
                break
            prev.first.click()
            page.wait_for_timeout(1500)
        if not found:
            browser.close()
            return {
                "ok": False,
                "error": f"還元額明細で {grant_label}分 を開けませんでした",
                "target_month": target_month,
                "grant_month": grant_month,
            }

        rebate_text = page.inner_text("body")
        method = "tokuten"
        yen = parse_tokuten_yen(rebate_text)
        if yen is None:
            yen = parse_opening_balance(rebate_text)
            method = "opening_balance"
        if yen is None:
            browser.close()
            return {
                "ok": False,
                "error": (
                    f"{grant_label}分に特典行も開始残高も取れません。"
                    "付与前（翌月20日前）の可能性あり"
                ),
                "target_month": target_month,
                "grant_month": grant_month,
                "method": method,
            }

        # NEXCO ポイント（参考）
        nexco_pts = None
        try:
            page.goto(POINTS_URL, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(1200)
            pts_text = page.inner_text("body")
            nexco_pts = parse_nexco_points_for_usage(pts_text, target_month)
        except Exception:
            nexco_pts = None

        browser.close()

    note_bits = [
        f"smile-etc 自動取得: 利用月 {target_month} → 付与月 {grant_month}（翌月20日ルール）",
        f"取得方法={method}",
    ]
    if nexco_pts is not None:
        note_bits.append(f"NEXCOポイント（{target_month}分）+{nexco_pts:,}")
    if method == "opening_balance":
        note_bits.append("特典行なしのため還元額明細の開始残高から確定")

    return {
        "ok": True,
        "target_month": target_month,
        "grant_month": grant_month,
        "rebate_yen": yen,
        "savings_yen": yen,
        "asayu_trip_count": None,
        "asayu_rate_pct": None,
        "method": method,
        "nexco_points": nexco_pts,
        "note": "。".join(note_bits),
        "source": "smile-etc_auto",
    }


def apply_result(state: dict[str, Any], scraped: dict[str, Any], now: datetime) -> dict[str, Any]:
    result = {
        "at": now.isoformat(),
        "ok": True,
        "target_month": scraped["target_month"],
        "rebate_yen": scraped["rebate_yen"],
        "asayu_trip_count": scraped.get("asayu_trip_count"),
        "asayu_rate_pct": scraped.get("asayu_rate_pct")
        or rate_from_trip_count(scraped.get("asayu_trip_count")),
        "savings_yen": scraped.get("savings_yen", scraped["rebate_yen"]),
        "note": scraped.get("note") or "",
        "source": scraped.get("source") or "smile-etc_auto",
        "method": scraped.get("method"),
        "nexco_points": scraped.get("nexco_points"),
    }
    state["last_check_b"] = month_key(now)
    state["last_result_b"] = result
    upsert_rebate_history(state, result)
    state["last_auto_fetch_at"] = now.isoformat()
    state["last_auto_fetch_target"] = scraped["target_month"]
    return result


def push_dashboard() -> dict[str, Any]:
    py = Path.home() / "selenium_env" / "venv" / "bin" / "python"
    cmd = [str(py), str(REPO / "scripts" / "jarvis_dashboard_push.py"), "--watch-only"]
    env = os.environ.copy()
    # private env for supabase
    if PRIVATE_ENV.is_file():
        for k, v in load_dotenv(PRIVATE_ENV).items():
            env.setdefault(k, v)
    proc = subprocess.run(
        cmd,
        cwd=str(REPO),
        env=env,
        capture_output=True,
        text=True,
        timeout=180,
    )
    return {
        "returncode": proc.returncode,
        "stdout_tail": (proc.stdout or "")[-800:],
        "stderr_tail": (proc.stderr or "")[-400:],
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="ETC 平日朝夕還元額の自動取得")
    ap.add_argument("--dry-run", action="store_true", help="取得のみ（state/push しない）")
    ap.add_argument("--apply", action="store_true", help="etc_monthly.json に反映")
    ap.add_argument("--push", action="store_true", help="dashboard_push --watch-only")
    ap.add_argument("--force", action="store_true", help="履歴にあっても再取得・上書き")
    ap.add_argument(
        "--target-month",
        default="",
        help="利用月 YYYY-MM（省略時: 定例窓なら前月）",
    )
    ap.add_argument("--headed", action="store_true", help="ブラウザ表示")
    args = ap.parse_args()

    now = datetime.now(JST)
    env = load_dotenv(PRIVATE_ENV)
    state = load_state()

    disabled = (
        state.get("disabled")
        or env.get("JARVIS_ETC_MONTHLY_DISABLE", "").strip().lower() in ("1", "true", "yes")
        or env.get("JARVIS_ETC_REBATE_AUTO_DISABLE", "").strip().lower() in ("1", "true", "yes")
    )
    report: dict[str, Any] = {
        "now_jst": now.isoformat(),
        "window_day": now.day in AUTO_WINDOW_DAYS,
        "disabled": bool(disabled),
    }
    if disabled and not args.force:
        report["skipped"] = "disabled"
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0

    target = (args.target_month or "").strip() or default_target_month(now)
    if not target:
        report["skipped"] = (
            f"定例窓外（本日{now.day}日）。付与は利用月の翌月20日。"
            "手動は --target-month YYYY-MM"
        )
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0

    report["target_month"] = target
    report["grant_month"] = add_months(target, 1)

    if history_has(state, target) and not args.force:
        report["skipped"] = f"history already has {target}"
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0

    mid = env.get("ETC_MILEAGE_ID") or ""
    pw = env.get("ETC_MILEAGE_WEB_PASSWORD") or ""
    if not mid or not pw:
        report["ok"] = False
        report["error"] = "ETC_MILEAGE_ID / ETC_MILEAGE_WEB_PASSWORD 未設定"
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 2

    try:
        scraped = scrape_rebate(
            mileage_id=mid,
            password=pw,
            target_month=target,
            headless=not args.headed,
        )
    except Exception as e:
        report["ok"] = False
        report["error"] = str(e)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 1

    report["scrape"] = scraped
    if not scraped.get("ok"):
        report["ok"] = False
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 1

    report["ok"] = True
    if args.dry_run or not args.apply:
        if not args.apply:
            report["note"] = "取得のみ（--apply で state 反映）"
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0

    result = apply_result(state, scraped, now)
    save_state(state)
    report["applied"] = result

    if args.push:
        report["push"] = push_dashboard()

    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
