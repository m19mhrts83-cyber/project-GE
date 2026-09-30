#!/usr/bin/env python3
"""
Zaim 連携設定ページで、指定口座の「連携データを更新」を押す（Phase1.5）。

  cd ~/git-repos && set -a && source .env.jarvis_private && set +a
  /Users/matsunomasaharu2/selenium_env/venv/bin/python scripts/jarvis_zaim_bank_sync_manual.py --from-stale
  /Users/matsunomasaharu2/selenium_env/venv/bin/python scripts/jarvis_zaim_bank_sync_manual.py --names '★MUFG(アパート経営)'

要: 先に zaim_budget_apply.py --login（セッション切れ時）。
YAML の automation: off / cooldown は --from-stale 時に尊重。
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import yaml
from playwright.sync_api import sync_playwright

REPO = Path(__file__).resolve().parents[1]
ZAIM_DIR = REPO / "215_kamiooya" / "C1_cursor" / "finance" / "zaim_budget_sync"
STATE_PATH = REPO / ".jarvis_state" / "zaim_bank_sync.json"
AUTO_STATE = REPO / ".jarvis_state" / "zaim_bank_auto.json"
CFG_PATH = REPO / "config" / "zaim_bank_sync_watch.yaml"
sys.path.insert(0, str(ZAIM_DIR))
import zaim_budget_apply as zaim  # noqa: E402

JST = ZoneInfo("Asia/Tokyo")
ONLINE = "https://zaim.net/online_accounts"
DEFAULT_NAMES = [
    "★MUFG(アパート経営)",
    "★三井住友銀行 刈谷",
    "住信 SBI ネット銀行",
]
OTP_MARKERS = (
    "ワンタイム",
    "認証コード",
    "確認コード",
    "セキュリティコード",
    "SMS",
    "画像認証",
    "キャプチャ",
    "追加認証",
    "本人確認",
)


def now_iso() -> str:
    return datetime.now(JST).strftime("%Y-%m-%dT%H:%M:%S%z")


def dismiss(page) -> None:
    page.keyboard.press("Escape")
    page.wait_for_timeout(300)


def load_cfg() -> dict[str, Any]:
    if not CFG_PATH.is_file():
        return {}
    return yaml.safe_load(CFG_PATH.read_text(encoding="utf-8")) or {}


def load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def account_by_match(cfg: dict[str, Any], name: str) -> dict[str, Any] | None:
    for acc in cfg.get("accounts") or []:
        if not isinstance(acc, dict):
            continue
        m = str(acc.get("match") or "")
        if m and (m in name or name in m):
            return acc
    return None


def in_cooldown(auto: dict[str, Any], name: str, hours: int) -> bool:
    attempts = auto.get("attempts") or {}
    row = attempts.get(name) or {}
    at = str(row.get("at") or "")
    if len(at) < 10:
        return False
    try:
        dt = datetime.fromisoformat(at.replace("+0900", "+09:00"))
    except ValueError:
        return False
    return datetime.now(JST) - dt < timedelta(hours=max(1, hours))


def names_from_stale(*, respect_automation: bool = True) -> list[str]:
    """state の stale から更新対象名を取る。automation:off / cooldown は除外。"""
    cfg = load_cfg()
    auto = load_json(AUTO_STATE)
    cooldown_h = int(cfg.get("auto_update_cooldown_hours") or 20)
    data = load_json(STATE_PATH)
    out: list[str] = []
    seen: set[str] = set()
    for row in data.get("stale") or []:
        if not isinstance(row, dict):
            continue
        name = str(row.get("match") or row.get("csv_name") or "").strip()
        if not name or name in seen:
            continue
        acc = account_by_match(cfg, name)
        if respect_automation and acc:
            if acc.get("unlinkable"):
                continue
            if str(acc.get("automation") or "").lower() in ("off", "false", "0", "no"):
                continue
        if respect_automation and in_cooldown(auto, name, cooldown_h):
            continue
        seen.add(name)
        out.append(name)
    return out


def detect_auth_blocker(page) -> str | None:
    try:
        body = page.locator("body").inner_text(timeout=2000)
    except Exception:
        return None
    for m in OTP_MARKERS:
        if m in body:
            if "画像" in m or "キャプチャ" in m:
                return "captcha"
            return "otp_required"
    return None


def update_one(page, name: str) -> dict:
    name_el = page.locator('[class*="accountName"]', has_text=name).first
    if name_el.count() == 0:
        return {"name": name, "ok": False, "reason": "not found"}
    name_el.scroll_into_view_if_needed()
    page.wait_for_timeout(400)
    pulldown = name_el.locator(
        'xpath=following::a[contains(@class,"PulldownMenu")][1]'
    )
    if pulldown.count() == 0:
        return {"name": name, "ok": False, "reason": "no pulldown"}
    pulldown.click()
    page.wait_for_timeout(600)
    clicked = None
    for label in ("連携データを更新", "データを更新する", "データを更新"):
        cand = page.get_by_text(label, exact=False)
        for i in range(cand.count()):
            el = cand.nth(i)
            if el.is_visible():
                el.click()
                clicked = label
                break
        if clicked:
            break
    page.wait_for_timeout(3500)
    blocker = detect_auth_blocker(page)
    if blocker:
        dismiss(page)
        return {"name": name, "ok": False, "reason": blocker, "clicked": clicked}
    dismiss(page)
    return {"name": name, "ok": bool(clicked), "clicked": clicked}


def record_attempts(results: list[dict]) -> None:
    auto = load_json(AUTO_STATE)
    attempts = dict(auto.get("attempts") or {})
    for r in results:
        name = str(r.get("name") or "")
        if not name:
            continue
        attempts[name] = {
            "at": now_iso(),
            "ok": bool(r.get("ok")),
            "reason": r.get("reason"),
        }
    auto["attempts"] = attempts
    auto["updated_at"] = now_iso()
    save_json(AUTO_STATE, auto)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--names",
        nargs="*",
        default=None,
        help="口座名（部分一致）。省略時は DEFAULT_NAMES（--from-stale 時は stale のみ）",
    )
    ap.add_argument(
        "--from-stale",
        action="store_true",
        help=".jarvis_state/zaim_bank_sync.json の stale 口座だけ更新",
    )
    ap.add_argument(
        "--ignore-automation",
        action="store_true",
        help="YAML automation:off / cooldown を無視",
    )
    ap.add_argument("--headed", action="store_true", default=True)
    ap.add_argument("--headless", action="store_true")
    args = ap.parse_args(argv)
    headed = not args.headless

    if args.from_stale:
        names = (
            list(args.names)
            if args.names
            else names_from_stale(respect_automation=not args.ignore_automation)
        )
        if not names:
            print(
                json.dumps(
                    {
                        "ok": True,
                        "results": [],
                        "note": "no stale accounts (or all skipped by automation/cooldown)",
                    },
                    ensure_ascii=False,
                )
            )
            return 0
    else:
        names = list(args.names) if args.names else list(DEFAULT_NAMES)

    if not zaim.STORAGE_STATE.is_file():
        print(f"先に login: {zaim.STORAGE_STATE}", file=sys.stderr)
        return 1

    results = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=not headed)
        ctx = browser.new_context(storage_state=str(zaim.STORAGE_STATE))
        page = ctx.new_page()
        page.goto(ONLINE, wait_until="networkidle", timeout=90000)
        page.wait_for_timeout(2000)
        dismiss(page)
        if zaim.is_login_page(page) or "kufu.jp/signin" in page.url:
            print("セッション切れ。zaim_budget_apply.py --login を先に。", file=sys.stderr)
            browser.close()
            return 2
        for name in names:
            print(f"# update {name}", file=sys.stderr)
            results.append(update_one(page, name))
            if "online_accounts" not in page.url:
                page.goto(ONLINE, wait_until="domcontentloaded")
                page.wait_for_timeout(2000)
                dismiss(page)
        zaim.save_storage_state(ctx)
        browser.close()
    record_attempts(results)
    print(json.dumps(results, ensure_ascii=False, indent=2))
    if any(r.get("reason") in ("otp_required", "captcha") for r in results):
        return 3
    return 0 if all(r.get("ok") for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
