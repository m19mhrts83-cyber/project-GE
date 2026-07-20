#!/usr/bin/env python3
"""SBI証券 Vポイントアッププログラム — 初期設定・状態確認・Vポイント投資補助。

  python scripts/jarvis_sbi_vpoint_up_setup.py --status
  python scripts/jarvis_sbi_vpoint_up_setup.py --setup
  python scripts/jarvis_sbi_vpoint_up_setup.py --invest [--points 10000]
  python scripts/jarvis_sbi_vpoint_up_setup.py --open-olive

.env.jarvis_private: SBI_SEC_*, VPASS_*, OLIVE_FLEXIBLE_PAY_CREDIT_LAST4
"""
from __future__ import annotations

import argparse
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

from playwright.sync_api import Page, TimeoutError as PlaywrightTimeout, sync_playwright

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from car_loan.chrome_cdp import cdp_ready, open_in_chrome, start_cdp_chrome  # noqa: E402
from car_loan.env_state import ENV_FILE, load_env  # noqa: E402
from jarvis_sbi_bank_chuukai import (  # noqa: E402
    CDP_PORT as CHUUKAI_PORT,
    PROFILE as CHUUKAI_PROFILE,
    SBI_CUSTOMER_SETTING,
    SBI_LOGIN_ENTRY,
    _detect_intermediary,
    _print_customer_info,
    _sbi_login,
    _wait_past_login,
)

CDP_PORT = 9228
PROFILE = Path.home() / ".jarvis_state" / "chrome_sbi_chuukai"

POINT_TOP = (
    "https://www.sbisec.co.jp/ETGate/WPLETmgR001Control"
    "?OutSide=on&getFlg=on&burl=search_home&cat1=home&cat2=service"
    "&dir=service&file=home_point_01.html"
)
VPOINT_SERVICE = (
    "https://www.sbisec.co.jp/ETGate/WPLETmgR001Control"
    "?OutSide=on&getFlg=on&burl=search_home&cat1=home&cat2=service"
    "&dir=service&file=home_v-point.html"
)
VPOINT_UP_PROGRAM = (
    "https://www.sbisec.co.jp/ETGate/WPLETmgR001Control"
    "?OutSide=on&getFlg=on&burl=search_home&cat1=home&cat2=service"
    "&dir=service&file=home_point_up_program.html"
)
NISA_TOP = (
    "https://site2.sbisec.co.jp/ETGate/?_ControlID=WPLETacR001Control"
    "&_PageID=DefaultPID&_DataStoreID=DSWPLETacR001Control"
    "&_ActionID=DefaultAID&OutSide=on&getFlg=on&path=account%2Fnisa%2Ftop"
)
MAINPOINT_SETTING = (
    "https://site2.sbisec.co.jp/ETGate/?OutSide=on&_ControlID=WPLETsmR001Control"
    "&_DataStoreID=DSWPLETsmR001Control&_PageID=WPLETsmR001Sdtl15"
    "&_ActionID=noLogin&sw_param1=account&sw_param2=registinfo&sw_param3=point"
    "&sw_param4=mainpoint&sw_param5=setting&getFlg=on"
)
POINT_SERVICE_DO = "https://site0.sbisec.co.jp/marble/account/registinfo/point/service.do"
POINT_RESERVE_SETTING = (
    "https://site0.sbisec.co.jp/marble/account/registinfo/point/reserveBuySetting/setting.do"
)
VPOINT_INVEST = (
    "https://site2.sbisec.co.jp/ETGate/?_ControlID=WPLETsmR001Control"
    "&_PageID=WPLETsmR001Sdtl12&_DataStoreID=DSWPLETsmR001Control"
    "&OutSide=on&getFlg=on&sw_page=WNS001&sw_param1=trade&sw_param2=fund"
    "&sw_param3=vpoint&sw_param4=top"
)
OLIVE_ASSET = "https://www.smbc.co.jp/kojin/olive/special/feature/"
SMBC_CHUUKAI_APPLY = "https://www.smbc.co.jp/kojin/asset-management/sbi/course_change/"


@dataclass
class SetupStatus:
    intermediary: str = "不明"
    main_point_v: bool = False
    vpoint_card: bool = False
    vpass_auth: bool = False
    smbc_card: bool = False
    nisa_hints: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    vpoint_balance: str = ""
    vpoint_used_this_month: str = ""


def _login_sbi(page: Page, env: dict[str, str], ctx, *, wait_otp_sec: int = 300) -> bool:
    user = env.get("SBI_SEC_USER", "")
    pw = env.get("SBI_SEC_LOGIN_PASSWORD", "")
    if not user or not pw:
        print("SBI_SEC_USER / SBI_SEC_LOGIN_PASSWORD が未設定です", file=sys.stderr)
        return False
    page.goto(SBI_LOGIN_ENTRY, wait_until="domcontentloaded", timeout=90000)
    _sbi_login(page, user, pw)
    if not _wait_past_login(page, wait_otp_sec):
        print("⚠️ SBI ログイン未完了（OTP等は Chrome で完了後に再実行）")
        return False
    # marble (site0) セッション確立
    page.goto(MAINPOINT_SETTING, wait_until="domcontentloaded", timeout=90000)
    page.wait_for_timeout(1500)
    return "login.sbisec.co.jp" not in page.url


def _ensure_marble_session(page: Page) -> bool:
    page.goto(MAINPOINT_SETTING, wait_until="domcontentloaded", timeout=90000)
    page.wait_for_timeout(1500)
    return "login.sbisec.co.jp" not in page.url


def _click_first(page: Page, patterns: list[str]) -> bool:
    for pat in patterns:
        for kind in ("link", "button"):
            loc = page.get_by_role(kind, name=re.compile(pat))
            if loc.count():
                try:
                    el = loc.first
                    if el.is_visible():
                        el.click()
                        page.wait_for_timeout(2000)
                        return True
                except Exception:
                    pass
        loc = page.locator(f"a:has-text('{pat}'), button:has-text('{pat}')")
        if loc.count():
            try:
                if loc.first.is_visible():
                    loc.first.click()
                    page.wait_for_timeout(2000)
                    return True
            except Exception:
                pass
    return False


def _body_flags(page: Page) -> dict[str, bool]:
    try:
        text = page.inner_text("body")
    except Exception:
        text = ""
    html = page.content() if text else ""
    combined = text + html
    return {
        "main_v": bool(re.search(r"メインポイント.*Vポイント|Vポイント.*メイン", combined))
        or ("青と黄色" in combined and "メインポイント" in combined),
        "v_card_done": bool(
            re.search(r"Vポイントカード.*登録済|登録済.*Vポイント|カード番号.*登録済", combined)
        ),
        "vpass_done": bool(
            re.search(r"Vポイント認証.*済|認証済|SMBC ID.*連携済|Vpass.*連携済", combined)
        ),
        "smbc_card": bool(re.search(r"6777|Ｏｌｉｖｅ.*ＩＮＦ|Olive.*INF", combined)),
        "v_invest": bool(re.search(r"Vポイント投資", combined)),
    }


def _reuse_logged_in_page(ctx) -> Page:
    for pg in ctx.pages:
        if "sbisec.co.jp" in pg.url and "login.sbisec.co.jp" not in pg.url:
            return pg
    return ctx.new_page()


def _parse_nisa_evaluation(page: Page) -> list[str]:
    page.goto(NISA_TOP, wait_until="domcontentloaded", timeout=90000)
    page.wait_for_timeout(2500)
    hints: list[str] = []
    for line in page.inner_text("body").splitlines():
        s = line.strip()
        if re.search(r"[0-9,]+", s) and any(
            k in s for k in ("評価", "保有", "投資枠", "NISA", "投資信託", "つみたて")
        ):
            hints.append(s[:120])
    return hints


def _read_mainpoint_status(page: Page) -> dict[str, bool]:
    page.goto(MAINPOINT_SETTING, wait_until="domcontentloaded", timeout=90000)
    page.wait_for_timeout(2500)
    text = page.inner_text("body")
    return {
        "main_v": "Vポイント" in text and "メインポイント" in text,
        "v_card_done": "Vポイントカード登録済み" in text,
        "vpass_done": "三井住友カードVポイント認証済み" in text,
        "smbc_card": bool(re.search(r"6777|Ｏｌｉｖｅ.*ＩＮＦ|Olive.*INF", text)),
    }


def _read_point_service(page: Page) -> dict[str, str]:
    _ensure_marble_session(page)
    page.goto(POINT_SERVICE_DO, wait_until="domcontentloaded", timeout=90000)
    page.wait_for_timeout(2500)
    text = page.inner_text("body")
    bal = ""
    m = re.search(r"保有Vポイント\s*([\d,]+)\s*ポイント", text)
    if m:
        bal = m.group(1)
    used = ""
    m2 = re.search(r"今月の利用履歴[：:]\s*([\d,]+)\s*ポイント", text)
    if m2:
        used = m2.group(1)
    return {"balance": bal, "used_month": used, "text": text}


def check_status(page: Page) -> SetupStatus:
    st = SetupStatus()
    _print_customer_info(page)
    st.intermediary = _detect_intermediary(page)

    flags = _read_mainpoint_status(page)
    st.main_point_v = flags["main_v"]
    st.vpoint_card = flags["v_card_done"]
    st.vpass_auth = flags["vpass_done"]
    st.smbc_card = flags["smbc_card"]

    ps = _read_point_service(page)
    st.vpoint_balance = ps["balance"]
    st.vpoint_used_this_month = ps["used_month"]
    if ps["balance"]:
        st.notes.append(f"保有Vポイント {ps['balance']}pt")
    if ps["used_month"] is not None and ps["used_month"] != "":
        st.notes.append(f"今月のポイント利用 {ps['used_month']}pt")

    st.nisa_hints = _parse_nisa_evaluation(page)

    return st


def _setup_main_point(page: Page) -> bool:
    flags = _read_mainpoint_status(page)
    if flags["main_v"] and flags["v_card_done"]:
        print("📎 Step01 は設定済み（メインポイント=Vポイント）")
        return True
    page.goto(POINT_TOP, wait_until="domcontentloaded", timeout=90000)
    page.wait_for_timeout(2000)
    if _click_first(page, [r"メインポイント", r"ポイントサービス", r"メインポイント設定"]):
        page.wait_for_timeout(2000)
    if _click_first(page, [r"Vポイント", r"青と黄色"]):
        page.wait_for_timeout(1500)
    if _click_first(page, [r"設定する", r"変更する", r"登録", r"次へ", r"確認"]):
        page.wait_for_timeout(2000)
    return _body_flags(page)["main_v"]


def _setup_vpoint_card(page: Page, env: dict[str, str]) -> bool:
    flags = _read_mainpoint_status(page)
    if flags["v_card_done"]:
        print("📎 Step02 は設定済み（Vポイントカード登録済み）")
        return True
    page.goto(VPOINT_SERVICE, wait_until="domcontentloaded", timeout=90000)
    if not _click_first(page, [r"Vポイントカード登録", r"Vポイントカード"]):
        return False
    page.wait_for_timeout(2000)
    # 規約同意
    for sel in ["#agree", "input[type='checkbox']"]:
        loc = page.locator(sel)
        if loc.count():
            try:
                if loc.first.is_visible() and not loc.first.is_checked():
                    loc.first.check(force=True)
            except Exception:
                pass
    trade_pw = env.get("SBI_SEC_TRADE_PASSWORD", "")
    if trade_pw:
        for sel in ["#trade-password", "input[name*='trade' i]", "input[type='password']"]:
            loc = page.locator(sel)
            if loc.count() and loc.first.is_visible():
                loc.first.fill(trade_pw)
                break
    _click_first(page, [r"同意", r"次へ", r"申込", r"登録", r"確認"])
    page.wait_for_timeout(3000)
    return _body_flags(page)["v_card_done"]


def _setup_vpass_auth(page: Page, env: dict[str, str], ctx) -> bool:
    flags = _read_mainpoint_status(page)
    if flags["vpass_done"]:
        print("📎 Step03 は設定済み（三井住友カードVポイント認証済み）")
        return True
    page.goto(VPOINT_SERVICE, wait_until="domcontentloaded", timeout=90000)
    page.wait_for_timeout(2000)
    if not _click_first(
        page,
        [
            r"三井住友カードVポイント認証",
            r"Vポイント認証",
            r"Vpass",
            r"SMBC ID",
        ],
    ):
        return False
    page.wait_for_timeout(3000)
    # Vpass タブ
    for p in ctx.pages:
        if re.search(r"smbc-card\.com|vpass", p.url):
            vpass_id = env.get("VPASS_ID", "")
            vpass_pw = env.get("VPASS_PASSWORD", "")
            if vpass_id and vpass_pw and "login" in p.url.lower() or "index" in p.url:
                try:
                    p.locator("input[type='text'], input:not([type])").first.fill(vpass_id)
                    p.locator("input[type='password']").first.fill(vpass_pw)
                    p.get_by_role("button", name=re.compile(r"ログイン")).first.click()
                    p.wait_for_timeout(3000)
                except Exception:
                    pass
            print(f"📎 Vpass タブ: {p.url[:80]} — 最終承認は Chrome で完了してください")
            return False
    return _body_flags(page)["vpass_done"]


def _used_points_this_month(ps: dict[str, str]) -> int:
    raw = (ps.get("used_month") or "0").replace(",", "")
    try:
        return int(raw)
    except ValueError:
        return 0


def _fill_trade_password(page: Page, env: dict[str, str]) -> bool:
    trade_pw = env.get("SBI_SEC_TRADE_PASSWORD", "")
    if not trade_pw:
        return False
    for sel in [
        "#trade-password",
        "input[name*='trade' i]",
        "input[name*='torihiki' i]",
        "input[placeholder*='取引' i]",
    ]:
        loc = page.locator(sel)
        if loc.count() and loc.first.is_visible():
            loc.first.fill(trade_pw)
            return True
    pw = page.locator("input[type='password']")
    if pw.count() == 1 and pw.first.is_visible():
        pw.first.fill(trade_pw)
        return True
    return False


def _try_reserve_point_setting(page: Page, env: dict[str, str], points: int) -> bool:
    _ensure_marble_session(page)
    page.goto(POINT_RESERVE_SETTING, wait_until="domcontentloaded", timeout=90000)
    page.wait_for_timeout(2500)
    if "login.sbisec.co.jp" in page.url:
        return False
    print(f"📎 ポイント利用設定: {page.url[:100]}")
    body = page.inner_text("body")
    if "メンテナンス" in body and "24:00" in body:
        print("⚠️ メンテナンス時間帯（毎営業日 24:00〜翌2:00頃は設定変更不可）")
        return False
    # 投資信託 積立 — ポイント利用する + 毎月上限
    try:
        page.locator("input[name='usePointSettingFundInput'][value='used']").check(force=True)
        page.locator("input[name='usePointNumberSettingFundInput'][value='someUsed']").check(force=True)
        page.locator("input[name='upperLimitFund']").fill(str(points))
    except Exception as e:
        print(f"⚠️ フォーム入力失敗: {e}")
        return False
    if not _fill_trade_password(page, env):
        print("⚠️ SBI_SEC_TRADE_PASSWORD 未設定または入力欄なし")
    btn = page.get_by_role("button", name=re.compile(r"設定する"))
    if not btn.count():
        btn = page.locator("input[type='submit'][value*='設定']")
    if btn.count() and btn.first.is_visible():
        btn.first.click()
        page.wait_for_timeout(3000)
        result = page.inner_text("body")
        if "設定しました" in result or "変更しました" in result or "完了" in result:
            print("✅ 積立ポイント利用設定を送信しました")
            return True
        if "エラー" in result or "入力してください" in result:
            print("⚠️ 設定画面にエラー表示あり — Chrome で確認してください")
        else:
            print("📎 設定ボタン押下済み — 結果を Chrome で確認してください")
            return True
    return False


def _try_vpoint_spot_invest(page: Page, env: dict[str, str], points: int) -> bool:
    page.goto(VPOINT_INVEST, wait_until="domcontentloaded", timeout=90000)
    page.wait_for_timeout(3000)
    if "login.sbisec.co.jp" in page.url:
        return False
    print(f"📎 Vポイント投資: {page.url[:100]}")
    body = page.inner_text("body")
    if "Vポイント投資" not in body and "ポイント" not in body:
        print("⚠️ Vポイント投資画面を開けませんでした")
        return False
    # つみたてNISA等の既存銘柄から買付へ
    if not _click_first(page, [r"買付", r"スポット", r"金額指定", r"注文"]):
        _click_first(page, [r"つみたて", r"NISA", r"投資信託"])
        page.wait_for_timeout(2000)
        _click_first(page, [r"買付", r"スポット", r"注文"])
    page.wait_for_timeout(2500)
    # ポイント利用を選択
    _click_first(page, [r"Vポイント", r"ポイント", r"ポイントを使"])
    pt_str = str(points)
    for sel in ["input[name*='point' i]", "input[id*='point' i]", "input[type='tel']"]:
        loc = page.locator(sel)
        if loc.count() and loc.first.is_visible():
            loc.first.fill(pt_str)
            break
    else:
        for sel in ["input[type='tel']", "input[type='number']", "input[type='text']"]:
            loc = page.locator(sel)
            for i in range(min(loc.count(), 8)):
                el = loc.nth(i)
                try:
                    if el.is_visible() and el.is_editable():
                        el.fill(pt_str)
                        break
                except Exception:
                    pass
    _fill_trade_password(page, env)
    if _click_first(page, [r"確認", r"次へ", r"注文", r"買付"]):
        page.wait_for_timeout(2500)
        _fill_trade_password(page, env)
        _click_first(page, [r"確定", r"注文", r"買付", r"実行"])
        page.wait_for_timeout(3000)
        return True
    return False


def _open_vpoint_invest(page: Page, env: dict[str, str], points: int) -> bool:
    ps = _read_point_service(page)
    used = _used_points_this_month(ps)
    if ps["balance"]:
        print(f"📎 保有Vポイント: {ps['balance']}pt / 今月利用: {used:,}pt")
    if used >= points:
        print(f"✅ 特典1達成済み（今月 {used:,}pt 利用）")
        return True
    if "login.sbisec.co.jp" in page.url:
        print("⚠️ 未ログインのため Vポイント投資を実行できません")
        return False
    print(f"📎 特典1: 当月 Vポイント投資であと {max(0, points - used):,}pt 以上が必要")
    ok = _try_vpoint_spot_invest(page, env, points)
    if not ok:
        print("📎 スポット買付が未完了 → 積立ポイント利用設定を試行…")
        ok = _try_reserve_point_setting(page, env, points)
    ps2 = _read_point_service(page)
    used2 = _used_points_this_month(ps2)
    if used2 >= points:
        print(f"✅ 特典1達成（今月利用 {used2:,}pt）")
        return True
    if not ok:
        print("📎 自動操作が途中まで。Chrome で買付またはポイント利用設定を確定してください")
    else:
        print(f"📎 操作送信済み。今月利用 {used2:,}pt — 約定後に再 --status で確認")
    return used2 >= points


def print_status_report(st: SetupStatus) -> None:
    print("\n📎 Vポイントアップ — 状態サマリー")
    print(f"   仲介口座: {st.intermediary}")
    print(f"   メインポイント=Vポイント: {'OK' if st.main_point_v else '要確認'}")
    print(f"   Vポイントカード登録: {'OK' if st.vpoint_card else '要確認'}")
    print(f"   Vpass/SMBC認証: {'OK' if st.vpass_auth else '要確認'}")
    print(f"   6777/INFカード: {'OK' if st.smbc_card else '要確認'}")
    if st.nisa_hints:
        print("   NISA関連:")
        for h in st.nisa_hints[:5]:
            print(f"     - {h}")
    if st.notes:
        print("   ポイント:")
        for n in st.notes[:5]:
            print(f"     - {n}")


def run(mode: str, *, wait_sec: int, otp_wait_sec: int, port: int, points: int) -> int:
    env = load_env(ENV_FILE)
    start_cdp_chrome(port, PROFILE, SBI_LOGIN_ENTRY)
    with sync_playwright() as pw:
        browser = pw.chromium.connect_over_cdp(f"http://127.0.0.1:{port}")
        ctx = browser.contexts[0] if browser.contexts else browser.new_context(locale="ja-JP")
        page = ctx.new_page()
        if not _login_sbi(page, env, ctx, wait_otp_sec=otp_wait_sec):
            time.sleep(wait_sec)
            return 1

        if mode == "status":
            st = check_status(page)
            print_status_report(st)
        elif mode == "setup":
            print("📎 Step01 メインポイント → Vポイント…")
            _setup_main_point(page)
            print("📎 Step02 Vポイントカード登録…")
            _setup_vpoint_card(page, env)
            print("📎 Step03 Vpass/SMBC ID 認証…")
            _setup_vpass_auth(page, env, ctx)
            print("📎 Step04 SMBC ID カード登録は Vpass 側で 6777/Olive INF を確認")
            st = check_status(page)
            print_status_report(st)
            print("\n📎 Olive 資産運用サービス: 三井住友銀行アプリで申込（--open-olive で案内URL）")
        elif mode == "invest":
            ok = _open_vpoint_invest(page, env, points)
            if ok:
                return 0
        else:
            return 1

        print(f"\n📎 Chrome は {wait_sec} 秒間開いたままです（port {port}）")
        time.sleep(wait_sec)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="SBI Vポイントアッププログラム設定補助")
    parser.add_argument("--status", action="store_true", help="仲介・設定状態を確認")
    parser.add_argument("--setup", action="store_true", help="初期設定01〜04を進める")
    parser.add_argument("--invest", action="store_true", help="Vポイント投資画面を開く")
    parser.add_argument("--points", type=int, default=10000, help="Vポイント投資のポイント数")
    parser.add_argument("--open-olive", action="store_true", help="Olive資産運用の案内URLを開く")
    parser.add_argument("--open-chuukai", action="store_true", help="仲介口座変更URLを開く")
    parser.add_argument("--port", type=int, default=CDP_PORT)
    parser.add_argument("--otp-wait-sec", type=int, default=120, help="OTP待機秒")
    parser.add_argument("--wait-sec", type=int, default=600)
    args = parser.parse_args()

    if args.open_olive:
        open_in_chrome(OLIVE_ASSET)
        print("📎 三井住友銀行アプリ → Olive → 資産運用サービス を申込してください")
        return 0
    if args.open_chuukai:
        open_in_chrome(SMBC_CHUUKAI_APPLY)
        return 0

    mode = "status"
    if args.setup:
        mode = "setup"
    elif args.invest:
        mode = "invest"

    try:
        return run(mode, wait_sec=args.wait_sec, otp_wait_sec=args.otp_wait_sec, port=args.port, points=args.points)
    except (PlaywrightTimeout, TimeoutError, RuntimeError) as e:
        print(f"❌ {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
