"""業者のメルマガを返信候補にしない（2026-11-21 松野さん「メルマガ。リアクション不要」）。"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from jarvis_kurashift_vendor_reply_triage import is_vendor_newsletter  # noqa: E402

NEWSLETTER_BODY = (
    "松野真治様<br>\n<br>\nこんにちは。<br>\n中央不動産浜松店です。<br>\n<br>\n"
    "本メールでは、不動産を購入される際に知っておきたい、基礎知識やお役立ち情報をお届けします。<br>\n"
    "毎号、1分ほどで読み終えていただける内容ですので、ご一読ください。<br>\n"
    "今回の記事は【不動産購入に関する消費税】というテーマです。"
)


class VendorNewsletterTest(unittest.TestCase):
    def test_newsletter_is_detected(self) -> None:
        self.assertTrue(is_vendor_newsletter("不動産購入に関する消費税", NEWSLETTER_BODY))

    def test_unsubscribe_footer(self) -> None:
        self.assertTrue(is_vendor_newsletter("新着物件のご案内", "今週の新着です。\n配信停止はこちら"))

    def test_personal_reply_is_kept(self) -> None:
        body = (
            "松野様\nお問い合わせありがとうございます。\n"
            "ご希望の条件に近い中古戸建が浜松市内に1件ございます。資料を添付いたします。\n"
            "ご検討のほどよろしくお願いいたします。"
        )
        self.assertFalse(is_vendor_newsletter("Re: 戸建て物件のご紹介のお願い", body))

    def test_empty(self) -> None:
        self.assertFalse(is_vendor_newsletter("", ""))


if __name__ == "__main__":
    unittest.main()
