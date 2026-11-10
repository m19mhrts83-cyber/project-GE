"""カード引落ウォッチ: 引落日が古い日付に戻らないこと。

2026-11 に起きたずれ:
- Vpass の「11月26日お支払い金額（未確定）」を拾えず、引落日が別の日付に化けた
- 10/22 の「お支払い日のご案内」メールを毎回読み直し、引落日を 10/26 に巻き戻した
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import jarvis_card_debit_watch as w

try:
    import playwright.sync_api  # noqa: F401
except ModuleNotFoundError:
    # 文字の読み取りだけを試す。ブラウザ操作は使わないので空の代役で足りる。
    import types

    _pw = types.ModuleType("playwright")
    _sync = types.ModuleType("playwright.sync_api")
    _sync.Page = object
    _sync.sync_playwright = None
    _sync.TimeoutError = TimeoutError
    _sync.Error = Exception
    _pw.sync_api = _sync
    sys.modules.setdefault("playwright", _pw)
    sys.modules.setdefault("playwright.sync_api", _sync)

import jarvis_vpass_payment_fetch as v

MYPAGE_UNCONFIRMED = (
    "ご利用状況 2026年11月9日現在\n"
    "11月26日お支払い金額（未確定）\n577,567 円\n"
    "お支払い金額の変更は11月24日まで"
)
MYPAGE_CONFIRMED = "8月26日お支払い金額 （確定）\n1,596,308円"


def mail_hit(notice="2026-10-22", due="2026-10-26", amount=None):
    return {
        "card_id": "olive_infinite",
        "label": "Olive Infinite（クレジット）",
        "primary": True,
        "amount_jpy": amount,
        "due_date": due,
        "notice_date": notice,
        "source_message_id": "m1",
        "subject": "お支払い日のご案内",
    }


def state_after_vpass(due="2026-11-26"):
    return {
        "cards": {
            "olive_infinite": {
                "id": "olive_infinite",
                "primary": True,
                "amount_jpy": 577567,
                "due_date": due,
                "due_source": "vpass_web",
                "notice_date": "2026-10-22",
            }
        }
    }


class VpassParse(unittest.TestCase):
    def test_unconfirmed_heading_gives_due_and_amount(self):
        r = v.parse_payment_from_text(MYPAGE_UNCONFIRMED)
        self.assertEqual(r["amount_jpy"], 577567)
        self.assertTrue(r["due_date"].endswith("-11-26"), r["due_date"])
        self.assertIs(r["amount_confirmed"], False)

    def test_confirmed_heading_still_works(self):
        r = v.parse_payment_from_text(MYPAGE_CONFIRMED)
        self.assertEqual(r["amount_jpy"], 1596308)
        self.assertTrue(r["due_date"].endswith("-08-26"), r["due_date"])
        self.assertIs(r["amount_confirmed"], True)


class MergeScanDue(unittest.TestCase):
    def test_same_old_mail_does_not_roll_due_back(self):
        s = w.merge_scan(state_after_vpass(), [mail_hit()])
        self.assertEqual(s["cards"]["olive_infinite"]["due_date"], "2026-11-26")
        self.assertEqual(s["cards"]["olive_infinite"]["amount_jpy"], 577567)

    def test_newer_mail_updates_due(self):
        s = w.merge_scan(
            state_after_vpass(due="2026-10-26"),
            [mail_hit(notice="2026-11-20", due="2026-11-26")],
        )
        self.assertEqual(s["cards"]["olive_infinite"]["due_date"], "2026-11-26")

    def test_newer_mail_wins_even_if_due_is_earlier(self):
        s = w.merge_scan(
            state_after_vpass(due="2026-11-26"),
            [mail_hit(notice="2026-11-20", due="2026-11-25")],
        )
        self.assertEqual(s["cards"]["olive_infinite"]["due_date"], "2026-11-25")

    def test_manual_due_is_kept(self):
        st = state_after_vpass()
        st["cards"]["olive_infinite"]["due_date_manual"] = "2026-11-27"
        st["cards"]["olive_infinite"]["due_date"] = "2026-11-27"
        s = w.merge_scan(st, [mail_hit(notice="2026-11-20", due="2026-11-26")])
        self.assertEqual(s["cards"]["olive_infinite"]["due_date"], "2026-11-27")


if __name__ == "__main__":
    unittest.main()
