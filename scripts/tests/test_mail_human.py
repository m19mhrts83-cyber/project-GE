#!/usr/bin/env python3
"""人が書いたメールの判定（ネットワーク不要）。2026-11-04 の実メールの形を元にした例。"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))

from jarvis_mail_human import has_strong_action_signal, looks_human_mail  # noqa: E402
from jarvis_night_triage_general import classify_general_kind  # noqa: E402


class LooksHumanMailTest(unittest.TestCase):
    def test_reply_thread(self) -> None:
        self.assertTrue(looks_human_mail("yokoi_yutaka@ex.meigin.co.jp", "RE: 融資相談", "松野様\nお世話になっております。"))

    def test_mobile_sender(self) -> None:
        self.assertTrue(looks_human_mail("a.b@ezweb.ne.jp", "本日のご面談のお礼と必要書類のご案内", "本日はありがとうございました。"))

    def test_addressed_company_mail(self) -> None:
        self.assertTrue(looks_human_mail("info@yamamurafudosan.jp", "山村不動産", "松野様\n先日はお問合せいただき"))

    def test_card_notice_with_name(self) -> None:
        body = "松野 真治 様\n出金がありました。\nこのメールは送信専用です。"
        self.assertFalse(looks_human_mail("post_master@netbk.co.jp", "出金のお知らせ", body))

    def test_promo_with_request_words(self) -> None:
        body = "ぜひご確認ください。お申し込みは期限までにお願いします。\n配信停止はこちら"
        self.assertFalse(looks_human_mail("smbc_info@msg.smbc.co.jp", "【Oliverなら全員対象！】", body))

    def test_personal_sender_without_address(self) -> None:
        # 担当者名のアドレスでも、宛名の無い販促は人が書いたものと見なさない
        self.assertFalse(looks_human_mail("azami.masaoka@vacationclub.com", "期間限定特別オファー【マリオット】", "特別なご案内です"))

    def test_service_notice_without_markers(self) -> None:
        self.assertFalse(looks_human_mail("mail-info@diamond.co.jp", "【特集】ランキング", "今週の特集です。"))

    def test_classify_uses_human_rule(self) -> None:
        self.assertEqual(classify_general_kind("【PayPayカード公式】キャンペーン", "ご確認ください。送信専用", "paypaycard-info@mail.paypay-card.co.jp"), "skim")
        self.assertEqual(classify_general_kind("富士見台物件について", "松野様\n物件の件でご連絡です。", "to-sirai@nakado.com"), "mail")


class StrongActionTest(unittest.TestCase):
    def test_revived(self) -> None:
        self.assertEqual(classify_general_kind("手続きの件", "ご承認をお願いします。", "service@ex.example.com"), "mail")
        self.assertTrue(has_strong_action_signal("service@ex.example.com", "ご返信のお願い", ""))
        self.assertFalse(has_strong_action_signal("service@ex.example.com", "案内", "ご返信は不要です。"))
        self.assertFalse(has_strong_action_signal("service@ex.example.com", "案内", "ご返信をいただいても回答できません"))

    def test_bulk_not_revived(self) -> None:
        body = "ご承認ください。\n配信停止はこちら"
        self.assertFalse(has_strong_action_signal("service@ex.example.com", "案内", body))
        self.assertEqual(classify_general_kind("案内", body, "service@ex.example.com"), "skim")

    def test_noreply_not_revived(self) -> None:
        self.assertFalse(has_strong_action_signal("noreply@ex.example.com", "ご承認ください", ""))
        self.assertEqual(classify_general_kind("ご承認ください", "", "noreply@ex.example.com"), "skim")

    def test_noise_from_not_revived(self) -> None:
        self.assertEqual(classify_general_kind("ご承認ください", "", "alerts@github.com"), "skim")

    def test_no_strong_word_unchanged(self) -> None:
        self.assertEqual(classify_general_kind("ご案内", "ご確認ください。", "service@ex.example.com"), "skim")

    def test_signup_approval_not_revived(self) -> None:
        f = "service@ex.example.com"
        self.assertFalse(has_strong_action_signal(f, "新規登録のご承認のお知らせ", ""))
        self.assertFalse(has_strong_action_signal(f, "通知", "新規登録が承認されました。"))
        # 新規登録を含んでも承認以外の強語は従来どおり
        self.assertTrue(has_strong_action_signal(f, "新規登録の件、ご返信ください", ""))
        self.assertTrue(has_strong_action_signal(f, "新規登録の時間割", ""))
        self.assertTrue(has_strong_action_signal(f, "ご承認ください", ""))

    def test_beyond_600_chars_ignored(self) -> None:
        self.assertFalse(has_strong_action_signal("service@ex.example.com", "案内", "あ" * 601 + "承認"))


if __name__ == "__main__":
    unittest.main()
