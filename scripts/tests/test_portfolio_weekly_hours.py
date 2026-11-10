"""資産週次: 早朝の時間外を「失敗」にしない（2026-11-10）。"""
from __future__ import annotations

import sys
import unittest
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import jarvis_mf_bloomo_balance as mf  # noqa: E402
import jarvis_portfolio_weekly as pw  # noqa: E402

BRANCH_ERR = '  - waiting for locator("#branchNo")'


def at(h: int, m: int) -> datetime:
    return datetime(2026, 11, 10, h, m, tzinfo=pw.JST)


class AkatsukiEarlyMorning(unittest.TestCase):
    def test_login_form_missing_at_5am_is_skip(self) -> None:
        skip, reason = pw.akatsuki_early_morning_skip(BRANCH_ERR, at(5, 11))
        self.assertTrue(skip)
        # 週次の hours_skip 判定（「時間外」）に掛かり、日中に取り直される
        self.assertIn("時間外", reason)

    def test_same_error_in_daytime_stays_error(self) -> None:
        self.assertFalse(pw.akatsuki_early_morning_skip(BRANCH_ERR, at(9, 10))[0])
        self.assertFalse(pw.akatsuki_early_morning_skip(BRANCH_ERR, at(5, 30))[0])

    def test_other_error_at_5am_stays_error(self) -> None:
        msg = "取得失敗: 債券金額を抽出できませんでした。"
        self.assertFalse(pw.akatsuki_early_morning_skip(msg, at(5, 19))[0])


class MoneyForwardMaintenance(unittest.TestCase):
    def test_maintenance_page_detected(self) -> None:
        self.assertTrue(mf.is_maintenance_page("メンテナンス中 | Maintenance", ""))
        self.assertFalse(mf.is_maintenance_page("マネーフォワード ME", "資産総額 1,000円"))

    def test_maintenance_is_skipped_not_error(self) -> None:
        rec = pw.rec_from_exc(
            RuntimeError("マネーフォワードがメンテナンス中（時間をおいて再実行）")
        )
        self.assertEqual(rec["status"], "skipped")
        self.assertIn("メンテナンス", rec["reason"])

    def test_not_logged_in_is_still_error(self) -> None:
        rec = pw.rec_from_exc(RuntimeError("MF 未ログイン。--save-session で…"))
        self.assertEqual(rec["status"], "error")


FINANCE = Path(__file__).resolve().parents[2] / "215_kamiooya" / "C1_cursor" / "finance"


def _src(name: str) -> str:
    return (FINANCE / name).read_text(encoding="utf-8")


def _load_func(name: str, file: str):
    """Playwright 無しの CI でも動くよう、対象の純粋関数だけ取り出して評価する。"""
    import ast

    tree = ast.parse(_src(file))
    node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == name)
    ns: dict = {}
    exec(compile(ast.Module(body=[node], type_ignores=[]), file, "exec"), ns)  # noqa: S102
    return ns[name]


class SonySuspended(unittest.TestCase):
    def test_suspension_notice_detected(self) -> None:
        fn = _load_func("sony_service_suspended", "sony_life_surrender_value.py")
        self.assertTrue(fn("お客さまWEBサービス 現在、お客さまWEBはご利用いただけません。"))
        self.assertFalse(fn("ログイン"))

    def test_suspension_is_skipped_not_error(self) -> None:
        rec = pw.rec_from_exc(RuntimeError("ソニー生命 お客さまWEB がサービス停止中です"))
        self.assertEqual(rec["status"], "skipped")
        # 時間外扱いではない（毎日フル再実行の引き金にしない）
        self.assertFalse(any(x in rec["reason"] for x in ("時間外", "メンテナンス", "9:00")))


class AkatsukiOtpWindow(unittest.TestCase):
    def test_fresh_send_ignores_previous_attempt_mail(self) -> None:
        fn = _load_func("otp_min_internal_date_ms", "akatsuki_bond_balance.py")
        sent = 1_800_000_000_000
        # 2分前の試行で届いたコードは対象外
        self.assertGreater(fn(sent, clicked_send=True), sent - 120_000)
        self.assertEqual(fn(sent, clicked_send=False), sent - 60_000)

    def test_shared_poller_skew_is_zeroed(self) -> None:
        self.assertIn('"SOLAR_LOAN_OTP_GMAIL_CLOCK_SKEW_MS"', _src("akatsuki_bond_balance.py"))


class MoneyForwardLoginUrls(unittest.TestCase):
    def test_needs_login(self) -> None:
        self.assertTrue(mf._needs_login("https://id.moneyforward.com/account_selector"))
        self.assertTrue(mf._needs_login("https://accounts.google.com/v3/signin/accountchooser"))
        self.assertFalse(mf._needs_login("https://moneyforward.com/accounts"))


if __name__ == "__main__":
    unittest.main()
