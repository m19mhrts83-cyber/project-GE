#!/usr/bin/env python3
"""定期払いチャンス（テイチャン）— 状況確認・抽選・通知。

ステップ:
  1. 追加で実行できる手続き候補を列挙（迷うものは confirm_needed）
  2. 抽選券の有無を確認
  3. 券があれば抽選し「抽選したよ」を通知

使い方:
  python scripts/jarvis_teiki_barai_chance.py --status
  python scripts/jarvis_teiki_barai_chance.py --run
  python scripts/jarvis_teiki_barai_chance.py --run --skip-draw
  python scripts/jarvis_teiki_barai_chance.py --run --force   # interval 無視
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from playwright.sync_api import Page, sync_playwright

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from car_loan.chrome_cdp import cdp_ready, start_cdp_chrome  # noqa: E402
from car_loan.env_state import ENV_FILE, load_env  # noqa: E402

JST = ZoneInfo("Asia/Tokyo")
REPO = Path(__file__).resolve().parents[1]
STATE_DIR = REPO / ".jarvis_state"
STATE_PATH = STATE_DIR / "teiki_barai_chance.json"
EXAMPLE_PATH = STATE_DIR / "teiki_barai_chance.example.json"

CDP_PORT = 9235
PROFILE = Path.home() / ".jarvis_state" / "chrome_teiki_barai"
TEIKI_URL = "https://teikibarai.smbc-card.com"
TEIKI_SSO = (
    "https://www.smbc-card.com/memx/force_login/index.html"
    "?strURL=https%3A%2F%2Fmall.smbc-card.com%2Flogin%2Fteikibarai%2F"
    "%3Fbackpath%3D%26cc%3D001%26goto%3D%252Fgift_info"
)
TEIKI_GIFT = "https://teikibarai.smbc-card.com/gift_info"
TEIKI_GUIDE = "https://teikibarai.smbc-card.com/guide"

SHOT_DIR = STATE_DIR / "teiki_barai_chance"
DEFAULT_INTERVAL_DAYS = 7

SKIP_DRAW_STATUSES = {
    "done",
    "excluded_keep_paypay",
    "confirm_needed",
    "awaiting_first_charge",
    "n/a",
}


def now_iso() -> str:
    return datetime.now(JST).isoformat(timespec="seconds")


def load_state() -> dict[str, Any]:
    if STATE_PATH.is_file():
        data = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    elif EXAMPLE_PATH.is_file():
        data = json.loads(EXAMPLE_PATH.read_text(encoding="utf-8"))
    else:
        data = {}
    data.setdefault("disabled", False)
    data.setdefault("interval_days", DEFAULT_INTERVAL_DAYS)
    data.setdefault("enrolled", "unknown")
    data.setdefault("services", [])
    data.setdefault("draw_history", [])
    return data


def save_state(state: dict[str, Any]) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _parse_iso(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=JST)
        return dt.astimezone(JST)
    except ValueError:
        return None


def is_due(state: dict[str, Any], force: bool = False) -> tuple[bool, str]:
    if force:
        return True, "force"
    if state.get("disabled"):
        return False, "disabled"
    interval = int(state.get("interval_days") or DEFAULT_INTERVAL_DAYS)
    last = _parse_iso(state.get("last_check_at"))
    if last is None:
        return True, "never_checked"
    tickets = state.get("ticket_count")
    if isinstance(tickets, int) and tickets > 0:
        return True, "tickets_pending"
    elapsed = datetime.now(JST) - last
    if elapsed >= timedelta(days=interval):
        return True, f"interval_{interval}d"
    remain = timedelta(days=interval) - elapsed
    return False, f"wait_{remain.days}d{remain.seconds // 3600}h"


def parse_card_mig(env: dict[str, str]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for k, v in sorted(env.items()):
        if not k.startswith("CARD_MIG_"):
            continue
        status = ""
        note = ""
        for part in str(v).split(";"):
            part = part.strip()
            if part.startswith("status:"):
                status = part[7:]
            elif part.startswith("note:"):
                note = part[5:]
        rows.append({"key": k, "status": status, "note": note})
    return rows


def step1_actionables(state: dict[str, Any], env: dict[str, str]) -> list[dict[str, str]]:
    """追加手続き候補。自動実行はしない（報告のみ）。"""
    out: list[dict[str, str]] = []
    for svc in state.get("services") or []:
        st = str(svc.get("status") or "")
        if st in ("confirm_needed", "confirm", "candidate", "in_progress", "awaiting_first_charge"):
            out.append(
                {
                    "id": str(svc.get("id") or ""),
                    "title": str(svc.get("title") or ""),
                    "status": st,
                    "note": str(svc.get("note") or ""),
                    "action": (
                        "verify_charge"
                        if st == "awaiting_first_charge"
                        else ("confirm" if st == "confirm_needed" else "review")
                    ),
                }
            )
    actionable_statuses = {
        "pending",
        "pending_card_change",
        "in_progress",
        "paused",
        "blocked_paypal_card_add",
        "pending_kitteini",
        "mail_received",
    }
    skip_keys = {"CARD_MIG_YMOBILE", "CARD_MIG_AICITY", "CARD_MIG_UQ"}
    known = {str(s.get("card_mig_key") or "") for s in (state.get("services") or [])}
    for row in parse_card_mig(env):
        if row["key"] in skip_keys or row["key"] in known:
            continue
        if row["status"] in actionable_statuses:
            out.append(
                {
                    "id": row["key"].lower(),
                    "title": row["key"].replace("CARD_MIG_", ""),
                    "status": row["status"],
                    "note": row["note"][:120],
                    "action": "confirm",
                }
            )
    return out


def _shot(page: Page, name: str) -> Path:
    SHOT_DIR.mkdir(parents=True, exist_ok=True)
    path = SHOT_DIR / f"{datetime.now():%Y%m%d_%H%M%S}_{name}.png"
    try:
        page.screenshot(path=str(path), full_page=True)
        print(f"📎 screenshot: {path}")
    except Exception as e:
        print(f"⚠️ screenshot failed: {e}", file=sys.stderr)
    return path


def _body(page: Page, n: int = 4000) -> str:
    try:
        return page.inner_text("body")[:n]
    except Exception:
        return ""


def _login_vpass(page: Page, vpass_id: str, vpass_pw: str) -> None:
    """テイチャン専用 SSO（force_login → カード選択 Olive INF → gift_info）。"""
    page.goto(TEIKI_SSO, wait_until="domcontentloaded", timeout=90000)
    time.sleep(1.5)

    if page.locator("input[name='userid']").count() > 0:
        print("📎 Vpass ログイン（テイチャン SSO）…")
        page.locator("input[name='userid']").first.fill(vpass_id)
        page.locator("input[name='password']").first.fill(vpass_pw)
        clicked = page.evaluate(
            """() => {
              const nodes = [...document.querySelectorAll('input[type=submit],button')];
              const btn = nodes.find(b => {
                const label = (b.value || b.innerText || '').trim();
                if (label !== 'ログイン') return false;
                if (b.disabled) return false;
                const r = b.getBoundingClientRect();
                return r.width > 0 && r.height > 0;
              });
              if (!btn) return false;
              btn.click();
              return true;
            }"""
        )
        if not clicked:
            page.locator("input[name='password']").first.press("Enter")
        page.wait_for_load_state("domcontentloaded", timeout=90000)
        time.sleep(2.5)

    body = _body(page, 2500)
    if "ログインするカードを選択" in body or "次へ進む" in body:
        for hint in ("Ｏｌｉｖｅ　ＩＮＦ", "Olive　INF", "ＩＮＦ", "INF", "インフィニット"):
            loc = page.locator("label,a,button,div,span").filter(has_text=re.compile(hint))
            if loc.count() == 0:
                continue
            try:
                loc.first.click(timeout=3000)
                time.sleep(0.8)
                print(f"📎 card selected ~/{hint}/")
                break
            except Exception:
                continue
        loc = page.locator("a,button,input[type='submit']").filter(
            has_text=re.compile(r"次へ進む|次へ")
        )
        for i in range(min(loc.count(), 3)):
            el = loc.nth(i)
            try:
                if el.is_visible():
                    el.click(timeout=4000)
                    page.wait_for_load_state("domcontentloaded", timeout=90000)
                    time.sleep(2)
                    print("📎 next after card select")
                    break
            except Exception:
                continue

    if "gift_info" not in page.url and "teikibarai" not in page.url:
        page.goto(TEIKI_GIFT, wait_until="domcontentloaded", timeout=90000)
        time.sleep(1.5)
    print(f"📎 after login: {page.url}")
    _shot(page, "after_login")


def _select_card_if_needed(page: Page) -> None:
    body = _body(page, 2000)
    if "次へ進む" not in body and "カードを選択" not in body:
        return
    # Olive / Infinite / フレキシブル を優先
    for hint in ("ＩＮＦ", "INF", "インフィニット", "フレキシブル", "Olive", "7887", "6777"):
        loc = page.locator("label,a,button,div,span").filter(has_text=re.compile(hint))
        if loc.count() == 0:
            continue
        try:
            loc.first.click(timeout=3000)
            time.sleep(0.8)
            break
        except Exception:
            continue
    for pat in (r"次へ進む", r"次へ", r"決定"):
        loc = page.locator("a,button,input[type='submit']").filter(has_text=re.compile(pat))
        for i in range(min(loc.count(), 3)):
            el = loc.nth(i)
            try:
                if el.is_visible():
                    el.click(timeout=4000)
                    page.wait_for_load_state("domcontentloaded", timeout=60000)
                    time.sleep(1.2)
                    print(f"📎 card select: clicked ~/{pat}/")
                    return
            except Exception:
                continue


def _accept_terms_if_needed(page: Page) -> str:
    """規約同意画面なら同意を試みる。戻り値: yes / no / unknown"""
    body = _body(page, 3000)
    if "利用規約" in body or "同意" in body:
        # チェックボックス
        try:
            cbs = page.locator("input[type='checkbox']")
            for i in range(min(cbs.count(), 5)):
                cb = cbs.nth(i)
                if cb.is_visible() and not cb.is_checked():
                    cb.check(timeout=2000)
        except Exception:
            pass
        for pat in (r"同意して.*利用", r"同意する", r"利用を開始"):
            loc = page.locator("a,button,input[type='submit']").filter(has_text=re.compile(pat))
            for i in range(min(loc.count(), 3)):
                el = loc.nth(i)
                try:
                    if el.is_visible():
                        el.click(timeout=4000)
                        page.wait_for_load_state("domcontentloaded", timeout=60000)
                        time.sleep(1.5)
                        print("📎 規約同意をクリック")
                        return "yes"
                except Exception:
                    continue
        if "同意" in body and ("抽選" not in body):
            return "no"
    if "抽選" in body or "ご利用中" in body or "サービス" in body:
        return "yes"
    return "unknown"


def _parse_counts(text: str) -> dict[str, Any]:
    tickets = None
    w_chance = None
    services = None
    # 公開トップの「全 248 サービス」を会員の利用件数と誤認しない
    if re.search(r"会員ログインはこちら|全\s*\n?\s*248\s*\n?\s*サービス", text):
        return {
            "ticket_count": None,
            "w_chance_tickets": None,
            "service_count": None,
            "has_draw_button": False,
            "public_landing": True,
        }
    m = re.search(r"今月の抽選券\s*(\d+)\s*枚", text)
    if m:
        tickets = int(m.group(1))
    if tickets is None:
        m = re.search(r"抽選券[^\d]{0,12}(\d+)\s*枚", text)
        if m:
            tickets = int(m.group(1))
    m2 = re.search(r"(?:W|Ｗ)チャンス[^\d]{0,12}(\d+)\s*枚", text)
    if m2:
        w_chance = int(m2.group(1))
    m3 = re.search(r"(?:ご利用中|対象|利用中)[^\d]{0,20}(\d+)\s*(?:件|サービス)", text)
    if m3:
        services = int(m3.group(1))
    if "抽選はできません" in text and tickets is None:
        tickets = 0
    return {
        "ticket_count": tickets,
        "w_chance_tickets": w_chance,
        "service_count": services,
        "has_draw_button": bool(
            re.search(r"プレゼント抽選|抽選をする|まとめて.*抽選", text)
        ),
        "public_landing": False,
    }


def _click_draw(page: Page) -> dict[str, Any]:
    """抽選ボタンを押して結果テキストを取る。"""
    result: dict[str, Any] = {"ok": False, "summary": "", "raw_snip": ""}
    patterns = [
        r"プレゼント抽選をする",
        r"抽選をする",
        r"まとめて.*チャン",
        r"抽選する",
    ]
    clicked = False
    for pat in patterns:
        loc = page.locator("a,button,input[type='submit']").filter(has_text=re.compile(pat))
        for i in range(min(loc.count(), 5)):
            el = loc.nth(i)
            try:
                if not el.is_visible() or not el.is_enabled():
                    continue
                el.click(timeout=5000)
                page.wait_for_load_state("domcontentloaded", timeout=90000)
                time.sleep(2)
                clicked = True
                print(f"📎 draw clicked ~/{pat}/")
                break
            except Exception:
                continue
        if clicked:
            break
    if not clicked:
        # evaluate fallback
        clicked = page.evaluate(
            """() => {
              const nodes = [...document.querySelectorAll('a,button,input[type=submit]')];
              const btn = nodes.find(b => {
                const t = (b.value || b.innerText || b.textContent || '').replace(/\\s+/g,'');
                return /プレゼント抽選|抽選をする|抽選する/.test(t);
              });
              if (!btn) return false;
              btn.click();
              return true;
            }"""
        )
        if clicked:
            page.wait_for_load_state("domcontentloaded", timeout=90000)
            time.sleep(2)
            print("📎 draw clicked (evaluate)")
    _shot(page, "after_draw")
    text = _body(page, 5000)
    result["raw_snip"] = text[:800]
    # 結果要約
    won = []
    for m in re.finditer(r"(\d+)\s*円分|(\d+)\s*pt|VポイントPayギフト", text):
        won.append(m.group(0))
    if re.search(r"残念|はずれ|外れ", text):
        won.append("はずれあり")
    if re.search(r"当選|当たり", text):
        won.append("当選あり")
    result["summary"] = " / ".join(won[:6]) if won else (text[:120].replace("\n", " ") or "結果テキスト取得弱")
    result["ok"] = clicked
    return result


def scrape_and_maybe_draw(
    page: Page,
    *,
    do_draw: bool,
) -> dict[str, Any]:
    # 会員なら gift_info を正
    if "logout" in _body(page, 500).lower() or "ログアウト" in _body(page, 800):
        if "gift_info" not in page.url:
            page.goto(TEIKI_GIFT, wait_until="domcontentloaded", timeout=90000)
            time.sleep(1.2)
    enrolled = "yes" if "ログアウト" in _body(page, 800) else _accept_terms_if_needed(page)
    _shot(page, "teiki_gift")
    text = _body(page, 5000)
    counts = _parse_counts(text)

    # お支払い履歴でサービス件数の目安
    service_count = counts.get("service_count")
    try:
        loc = page.locator("a,button").filter(has_text=re.compile(r"^お支払い履歴$"))
        if loc.count() and loc.first.is_visible():
            loc.first.click(timeout=4000)
            page.wait_for_load_state("domcontentloaded", timeout=60000)
            time.sleep(1.5)
            pay = _body(page, 3000)
            if "今月のお支払い明細はありません" in pay or re.search(r"お支払い金額\s*0\s*円", pay):
                service_count = 0
            page.goto(TEIKI_GIFT, wait_until="domcontentloaded", timeout=90000)
            time.sleep(1.0)
            text = _body(page, 5000)
            counts = _parse_counts(text)
    except Exception:
        pass

    if counts.get("public_landing"):
        enrolled = "unknown"
        print("⚠️ まだ公開ランディング（未ログイン）の可能性")
    out: dict[str, Any] = {
        "enrolled": enrolled,
        "ticket_count": counts["ticket_count"],
        "w_chance_tickets": counts["w_chance_tickets"],
        "service_count": service_count if service_count is not None else counts["service_count"],
        "page_url": page.url,
        "draw": None,
        "public_landing": bool(counts.get("public_landing")),
    }
    tickets = counts["ticket_count"] or 0
    w = counts["w_chance_tickets"] or 0
    total = tickets + w
    if counts.get("public_landing"):
        return out
    if do_draw and total > 0:
        draw = _click_draw(page)
        after = _parse_counts(_body(page, 4000))
        out["draw"] = {
            "at": now_iso(),
            "tickets_before": total,
            "tickets_used": total,
            "ok": draw.get("ok"),
            "results_summary": draw.get("summary"),
            "tickets_after": after.get("ticket_count"),
        }
        if after.get("ticket_count") is not None:
            out["ticket_count"] = after["ticket_count"]
        if after.get("w_chance_tickets") is not None:
            out["w_chance_tickets"] = after["w_chance_tickets"]
    elif do_draw and total == 0:
        print("📎 抽選券0枚のため抽選スキップ")
    return out


def format_report(
    *,
    actionables: list[dict[str, str]],
    scrape: dict[str, Any] | None,
    state: dict[str, Any],
    drew: bool,
) -> str:
    lines = ["📎 テイチャン（定期払いチャンス）"]
    lines.append(f"- 規約同意: {state.get('enrolled')}")
    sc = state.get("service_count")
    tc = state.get("ticket_count")
    wc = state.get("w_chance_tickets")
    lines.append(
        f"- 対象サービス数: {sc if sc is not None else '—'} · "
        f"抽選券: {tc if tc is not None else '—'}枚 · "
        f"Wチャンス: {wc if wc is not None else '—'}枚"
    )
    if actionables:
        lines.append(f"- Step1 追加候補: {len(actionables)}件")
        for a in actionables[:6]:
            lines.append(
                f"  · [{a.get('action')}] {a.get('title')} ({a.get('status')}) — {a.get('note','')[:60]}"
            )
    else:
        lines.append("- Step1 追加候補: なし（明確に進めるものなし／迷いは確認待ち）")

    if scrape is None:
        lines.append("- Step2/3: 画面取得スキップ（--status または認証不足）")
    else:
        lines.append(f"- Step2 抽選券確認: 済（url={scrape.get('page_url','')[:60]}）")
        if drew and scrape.get("draw"):
            d = scrape["draw"]
            lines.append(
                f"- Step3 抽選したよ: {d.get('results_summary') or '完了'} "
                f"（before={d.get('tickets_before')} after={d.get('tickets_after')}）"
            )
        elif drew:
            lines.append("- Step3 抽選: 試行したがボタン未検出 or 失敗")
        else:
            lines.append("- Step3 抽選: スキップ（券なし or --skip-draw）")

    # 除外・済の明示
    for svc in state.get("services") or []:
        if svc.get("id") == "ymobile":
            lines.append(f"- 除外: ワイモバイル（{svc.get('status')}）")
        if svc.get("id") == "aicity_water":
            st = svc.get("status")
            if st == "awaiting_first_charge":
                lines.append(
                    "- 水道: AICITYカード変更報告済だが Olive 実課金未検出"
                    "（Zaimは大垣共立引落）。次請求／AICITY登録カード確認"
                )
            else:
                lines.append(f"- 水道 AICITY: {st}")
    return "\n".join(lines)


def run_browser(*, do_draw: bool) -> dict[str, Any]:
    env = load_env(ENV_FILE)
    vpass_id = env.get("VPASS_ID", "")
    vpass_pw = env.get("VPASS_PASSWORD", "")
    if not vpass_id or not vpass_pw:
        raise RuntimeError("未設定: VPASS_ID / VPASS_PASSWORD")

    start_cdp_chrome(CDP_PORT, PROFILE, TEIKI_URL)
    if not cdp_ready(CDP_PORT):
        raise RuntimeError(f"CDP port {CDP_PORT} not ready")

    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(f"http://127.0.0.1:{CDP_PORT}")
        ctx = browser.contexts[0] if browser.contexts else browser.new_context()
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        _login_vpass(page, vpass_id, vpass_pw)
        return scrape_and_maybe_draw(page, do_draw=do_draw)


def apply_scrape_to_state(state: dict[str, Any], scrape: dict[str, Any]) -> None:
    state["last_check_at"] = now_iso()
    if scrape.get("enrolled") in ("yes", "no", "unknown"):
        state["enrolled"] = scrape["enrolled"]
    for key in ("ticket_count", "w_chance_tickets", "service_count"):
        if scrape.get(key) is not None:
            state[key] = scrape[key]
    draw = scrape.get("draw")
    if draw and draw.get("ok"):
        state["last_draw_at"] = draw.get("at") or now_iso()
        state["last_draw"] = draw
        state["last_notified_at"] = now_iso()
        hist = list(state.get("draw_history") or [])
        hist.insert(0, draw)
        state["draw_history"] = hist[:12]
        # SBI を confirm→counted 寄せ
        for svc in state.get("services") or []:
            if svc.get("id") == "sbi_tsumitate" and svc.get("status") == "confirm":
                svc["status"] = "confirm"
                svc["note"] = (svc.get("note") or "") + " · テイチャン画面確認済"


def print_status(state: dict[str, Any], env: dict[str, str]) -> None:
    due, reason = is_due(state)
    actionables = step1_actionables(state, env)
    print(
        json.dumps(
            {
                "due": due,
                "reason": reason,
                "enrolled": state.get("enrolled"),
                "service_count": state.get("service_count"),
                "ticket_count": state.get("ticket_count"),
                "w_chance_tickets": state.get("w_chance_tickets"),
                "last_check_at": state.get("last_check_at"),
                "last_draw_at": state.get("last_draw_at"),
                "last_draw": state.get("last_draw"),
                "interval_days": state.get("interval_days"),
                "actionables": actionables,
                "services": [
                    {
                        "id": s.get("id"),
                        "title": s.get("title"),
                        "status": s.get("status"),
                    }
                    for s in (state.get("services") or [])
                ],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


def main() -> int:
    ap = argparse.ArgumentParser(description="定期払いチャンス（テイチャン）")
    ap.add_argument("--status", action="store_true", help="state / due / 候補のみ")
    ap.add_argument("--run", action="store_true", help="画面確認＋券があれば抽選")
    ap.add_argument("--skip-draw", action="store_true", help="抽選しない（確認のみ）")
    ap.add_argument("--force", action="store_true", help="interval 無視")
    ap.add_argument("--dry-run", action="store_true", help="ブラウザなしで Step1 だけ")
    args = ap.parse_args()

    env = load_env(ENV_FILE)
    if env.get("JARVIS_TEIKI_BARAI_DISABLE") == "1":
        print("📎 テイチャン: 無効化（JARVIS_TEIKI_BARAI_DISABLE=1）")
        return 0

    state = load_state()
    if state.get("disabled"):
        print("📎 テイチャン: 無効化（state disabled）")
        return 0

    if args.status or (not args.run and not args.dry_run):
        print_status(state, env)
        if not args.run and not args.dry_run:
            return 0

    due, reason = is_due(state, force=args.force or args.dry_run)
    if not due and args.run and not args.force:
        print(f"📎 テイチャン: 間隔内のためスキップ（{reason}）。--force で実行可")
        print_status(state, env)
        return 0

    actionables = step1_actionables(state, env)
    scrape: dict[str, Any] | None = None
    drew = False

    if args.dry_run:
        print(format_report(actionables=actionables, scrape=None, state=state, drew=False))
        return 0

    try:
        scrape = run_browser(do_draw=not args.skip_draw)
        apply_scrape_to_state(state, scrape)
        drew = bool(scrape.get("draw") and scrape["draw"].get("ok"))
        if not args.skip_draw and not drew:
            # 券0
            tc = scrape.get("ticket_count")
            if tc == 0 or tc is None:
                state["last_check_at"] = now_iso()
        save_state(state)
    except Exception as e:
        print(f"⚠️ テイチャン取得失敗: {e}", file=sys.stderr)
        print(format_report(actionables=actionables, scrape=None, state=state, drew=False))
        return 1

    print(format_report(actionables=actionables, scrape=scrape, state=state, drew=drew))
    if drew:
        print("\n✅ 抽選したよ — ダッシュボード /vpoint のテイチャン欄にも反映されます（push 後）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
