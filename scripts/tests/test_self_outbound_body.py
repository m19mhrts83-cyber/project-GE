#!/usr/bin/env python3
"""自分発信メール（やり取りmdで「相手から返信」誤ラベル）の本文判定テスト（ネットワーク不要）。"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))

from jarvis_kurashift_re_inquiry_channel import looks_like_self_outbound_body  # noqa: E402

SELF_BODIES = [
    # GHA パートナー行（from_email 無し）で pending に残っていた型
    "ミニテック\n林 様\n\nお世話になっております。松野です。\n\n共用部アンペア変更の立ち会い完了のご連絡と…",
    "ミニテック大曽根支店\n林 様\n\nお世話になっております。松野です。\n\nGrandole志賀本通Ⅰ 105号室のゴミ出し…",
    "大野さま\n\nお世話になっております。\n株式会社リビングサポート松の松野です。\n\n先日LINEにて…",
    # 既存パターン
    "株式会社LEAF 管理部\n神野様\n\nお世話になっております。\nGrandole志賀本通Ⅰ オーナーの松野です。\n\n訂正のご連絡です。",
]

PARTNER_BODIES = [
    "株式会社リビングサポート松\n松野 真治　様\n\n\nいつも大変お世話になっております。\n日本総険 清水です。\n\n"
    "> お世話になっております。\n> 株式会社リビングサポート松の松野です。",
    "株式会社リビングサポート松 松野 真治 様 お世話になっております。公庫より連絡があり…",
    "松野　様\n\nお世話になります。\nLEAFの神野です。",
    "松野様\n\n大変お世話になっております。大野です。\n\n> お世話になっております。\n> 株式会社リビングサポート松の松野です。",
    "株式会社リビングサポート松\n代表取締役　松野 真治 様\n\nお世話になります。\nご連絡ありがとうございます。",
    "定額自動振込サービス振込受付のお知らせ 松野 真治 さま 定額自動振込サービスの登録内容にもとづき…",
]


class SelfOutboundBodyTests(unittest.TestCase):
    def test_self_bodies_detected(self):
        for b in SELF_BODIES:
            with self.subTest(b=b[:30]):
                self.assertTrue(looks_like_self_outbound_body(b))

    def test_partner_bodies_not_detected(self):
        for b in PARTNER_BODIES:
            with self.subTest(b=b[:30]):
                self.assertFalse(looks_like_self_outbound_body(b))


if __name__ == "__main__":
    unittest.main()
