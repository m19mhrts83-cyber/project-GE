#!/usr/bin/env python3
"""資料依頼の検出テスト（ネットワーク不要）。"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))

from jarvis_material_request import extract_material_requests  # noqa: E402

SHOKOKAI = """松野 真治　様

お世話になります。
リビングサポート松様につきまして、ご入金はございましたでしょうか。

マルケイ融資（個人）につきまして下記の書類のご準備をお願いします。

借入申込書（お渡ししたもの）
今期の試算表（９月末ないし８月末まで）
電子契約サービス利用申込書
返済・融資入金を希望する通帳の表紙及び見開き１ページ目のコピー
借入金明細（住宅ローンも）
２０２６年９月末の個人の事業用預金の残高を教えてください
営業実在確認書類（いずれか）

よろしくお願いいたします。
"""

SOKEN = """株式会社リビングサポート松
松野 真治　様

いつも大変お世話になっております。
日本総険 清水です。

下記追加資料のご提出・ご確認をお願いいたします。
＝＝＝
1. 物件住所が記載されているページ（または現行証券の全ページ）
2. 建物の所有者は「松野真治様」でよろしいでしょうか
＝＝＝
何卒よろしくお願い申し上げます。

2026年10月21日(水) 7:21 松野家 <matsuno.estate@gmail.com>:
> ご送付の資料一覧
> ・自分の引用は拾わない書類
"""

THANKS = """松野様

お世話になっております。
明日の14時から17時の間で立ち会うことになりました。
よろしくお願いいたします。
"""


class MaterialRequestTests(unittest.TestCase):
    def test_plain_list_after_lead(self):
        items = extract_material_requests(SHOKOKAI)
        self.assertIn("借入申込書（お渡ししたもの）", items)
        self.assertIn("電子契約サービス利用申込書", items)
        self.assertTrue(any("通帳" in i for i in items))

    def test_numbered_list_and_quote_ignored(self):
        items = extract_material_requests(SOKEN)
        self.assertTrue(any("物件住所" in i for i in items))
        self.assertFalse(any("引用" in i for i in items))

    def test_not_a_request(self):
        self.assertEqual(extract_material_requests(THANKS), [])


if __name__ == "__main__":
    unittest.main()
