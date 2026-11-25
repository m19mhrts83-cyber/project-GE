"""Vpass 残高の取得部品（614・2026-11-25）。値はすべて架空。"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))

import jarvis_vpass_balance_fetch as vb  # noqa: E402

MYPAGE = """\
Myページ
ご利用状況 2099年01月15日現在

01月27日お支払い金額 （確定）
12,345円

Vポイント

1,234 pt

最短有効期限： 2099/03/31
照会・交換
最大9,999円相当のVポイントがもらえる！キャンペーン
Vポイント祭　福福キャンペーン
"""


class ParseTest(unittest.TestCase):
    def test_parse(self):
        p = vb.parse_mypage_balance(MYPAGE)
        self.assertEqual(p, {"asof": "2099-01-15", "balance_pt": 1234, "nearest_expiry": "2099-03-31"})

    def test_parse_unreadable(self):
        p = vb.parse_mypage_balance("ログインしてください\nVポイントがもらえる")
        self.assertEqual(p, {"asof": None, "balance_pt": None, "nearest_expiry": None})

    def test_parse_invalid_date(self):
        p = vb.parse_mypage_balance("ご利用状況 2099年13月40日現在\nVポイント\n5 pt")
        self.assertIsNone(p["asof"])
        self.assertEqual(p["balance_pt"], 5)


class CompareTest(unittest.TestCase):
    def hist(self, at="2099-01-15T08:30:00+09:00", bal=1234):
        return {"fetched_at": at, "balance_pt": bal}

    def test_match_same_day(self):
        c = vb.compare_with_tsite("2099-01-15", 1234, self.hist())
        self.assertTrue(c["same_day"])
        self.assertIs(c["match"], True)

    def test_mismatch_same_day(self):
        c = vb.compare_with_tsite("2099-01-15", 1234, self.hist(bal=1200))
        self.assertIs(c["match"], False)

    def test_other_day_is_not_compared(self):
        c = vb.compare_with_tsite("2099-01-16", 1234, self.hist())
        self.assertFalse(c["same_day"])
        self.assertIsNone(c["match"])  # 不一致とは書かない

    def test_no_history(self):
        c = vb.compare_with_tsite("2099-01-15", 1234, None)
        self.assertIsNone(c["match"])
        self.assertEqual(c["reason"], "Tサイト履歴なし")

    def test_unreadable_vpass(self):
        c = vb.compare_with_tsite(None, None, self.hist())
        self.assertIsNone(c["match"])


class RecordTest(unittest.TestCase):
    def test_build_and_save_readback(self):
        rec = vb.build_record(vb.parse_mypage_balance(MYPAGE), "2099-01-15T09:00:00+09:00", None)
        self.assertTrue(rec["ok"])
        self.assertEqual(rec["source"], "vpass_mypage")
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "vpoint_vpass_balance.json"
            self.assertTrue(vb.save_verified(rec, path))
            self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["asof"], "2099-01-15")

    def test_not_ok_when_unreadable(self):
        rec = vb.build_record(vb.parse_mypage_balance("なし"), "2099-01-15T09:00:00+09:00", None)
        self.assertFalse(rec["ok"])

    def test_latest_tsite_history_picks_newest(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "vpoint_tsite_history_20990101.json").write_text(
                json.dumps({"fetched_at": "2099-01-01T00:00:00+09:00", "balance_pt": 1}), encoding="utf-8")
            new = Path(d) / "vpoint_tsite_history_20990115.json"
            new.write_text(json.dumps({"fetched_at": "2099-01-15T00:00:00+09:00", "balance_pt": 2}), encoding="utf-8")
            self.assertEqual(vb.latest_tsite_history(Path(d))["balance_pt"], 2)


if __name__ == "__main__":
    unittest.main()
