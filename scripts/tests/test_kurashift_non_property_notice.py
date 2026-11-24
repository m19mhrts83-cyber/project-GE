"""python3 -m unittest scripts/tests/test_kurashift_non_property_notice.py
非物件（案内・告知）判定のテスト。文面はすべて架空。DB・Gmail は呼ばない。
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import jarvis_kurashift_property_mail_match as m  # noqa: E402


class NonPropertyNoticeTest(unittest.TestCase):
    def test_seminar_notice_is_non_property(self):
        s = "【参加無料】不動産投資セミナー開催のお知らせ"
        t = f"{s}\n来月オンラインで勉強会を開きます。参加費は無料です。"
        self.assertTrue(m.is_non_property_notice(s, t))

    def test_newsletter_and_digest(self):
        for s in ("週刊メルマガ vol.12", "ニュースレター 11月号", "新着ダイジェスト"):
            self.assertTrue(m.is_non_property_notice(s, s + "\n今週の話題です。"), s)

    def test_notice_with_price_stays_property(self):
        s = "新着物件セミナー情報"
        t = f"{s}\n販売価格: 1,200万円\n所在地: 架空県架空市1丁目2番地"
        self.assertFalse(m.is_non_property_notice(s, t))

    def test_notice_with_layout_or_age_stays_property(self):
        self.assertFalse(m.is_non_property_notice("キャンペーン", "キャンペーン\n3LDK 築20年"))

    def test_weak_words_do_not_count_as_property(self):
        s = "戸建投資の勉強会のご案内"
        t = f"{s}\n戸建の利回りについて話します。参加費500万円ではありません。"
        self.assertTrue(m.is_non_property_notice(s, t))

    def test_plain_property_mail_not_flagged(self):
        s = "【新着】戸建 架空市 800万円"
        self.assertFalse(m.is_non_property_notice(s, s + "\n表面利回り 12%"))

    def test_no_marker_not_flagged(self):
        self.assertFalse(m.is_non_property_notice("ご連絡", "ご連絡です"))

    def test_clearly_out_of_scope_reason(self):
        s = "不動産セミナーのご案内"
        out, reason = m.clearly_out_of_scope(s, s + "\n本文のみ", 5.0)
        self.assertEqual((out, reason), (True, "non_property_notice"))


if __name__ == "__main__":
    unittest.main()
