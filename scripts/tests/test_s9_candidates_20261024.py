#!/usr/bin/env python3
"""S9 候補取り込み（action: s9_candidates）の単体テスト（ネットワーク不要）。"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))

import jarvis_s9_candidates_apply as s9  # noqa: E402

MD = """---
action: s9_candidates
source: s9
date: 2026-10-22
---
# S9 候補 2026-10-22（緑区優先）

## 1. 株式会社福島土地（緑区）
- 社名: 株式会社福島土地
- 所在: 〒458-0037 名古屋市緑区潮見が丘2丁目198-1
- 公式URL: https://www.fukushima-tochi.com/
- 連絡経路: メール fukushimatochi@gmail.com（公式サイト記載）／フォームは未確認
- 備考: 緑区地元密着。TEL 052-891-8008

## 2. 株式会社M-fort（豊明市）
- 所在: 〒470-1151 愛知県豊明市前後町善江1678-1
- 公式URL: https://m-fort.co.jp/
- 連絡経路: フォーム https://m-fort.co.jp/contact/ ／メールアドレスは未確認
- 備考: TEL 0562-85-2201

## 3. 髙松エステート（中部エリア）
- 所在: 名古屋拠点。緑区専用の管理案内ページあり
- 公式URL: https://takamatsuestate.jp/management/area/nagoyamidori
- 連絡経路: Webフォーム https://app.jibun-apps.jp/form/abc/new
- メモ: 全国大手（地場ではない）

## 4. 電話だけ不動産
- 所在: 名古屋市緑区鳴海町
- 連絡経路: TEL 052-000-0000 のみ

## 待ちの候補（台帳未反映）
- 10/22: 福島土地
"""


class ParseTests(unittest.TestCase):
    def setUp(self):
        meta, body = s9.parse_frontmatter(MD)
        self.assertEqual(meta["action"], "s9_candidates")
        self.rows = [s9.to_row(c, md_date="2026-10-22") for c in s9.parse_candidates(body)]

    def test_four_candidates_and_waiting_section_ignored(self):
        self.assertEqual(len(self.rows), 4)

    def test_email_candidate(self):
        r = self.rows[0]
        self.assertEqual(r["name"], "株式会社福島土地")
        self.assertEqual(r["channel"], "email")
        self.assertEqual(r["contact_email"], "fukushimatochi@gmail.com")
        self.assertEqual(r["property_area"], "緑区")
        self.assertEqual(r["phone"], "052-891-8008")
        self.assertEqual(r["status"], "pending")
        self.assertEqual(r["property_lane"], "midori_caramel")

    def test_form_candidate_and_area(self):
        r = self.rows[1]
        self.assertEqual(r["channel"], "web_form")
        self.assertEqual(r["contact_url"], "https://m-fort.co.jp/contact/")
        self.assertEqual(r["property_area"], "豊明市")

    def test_classify(self):
        existing = [{"name": "ハウ住む緑店", "url": "https://www.fukushima-tochi.com/x", "status": "pending"}]
        self.assertEqual(s9.classify(self.rows[0], existing)[0], "dup")  # 同じドメイン
        self.assertEqual(s9.classify(self.rows[1], [])[0], "add")
        self.assertEqual(s9.classify(self.rows[2], [])[0], "consult")  # 大手
        self.assertEqual(s9.classify(self.rows[3], [])[0], "consult")  # 電話のみ

    def test_consult_message_has_handoff_footer(self):
        msg = s9.build_consult([(self.rows[2], "メモに「大手」", "2026-10-22_s9_candidates.md")])
        self.assertTrue(msg.startswith("【相談】S9"))
        self.assertIn("次: Jarvisに依頼", msg)
        self.assertIn("橋渡し:", msg)


class AreaTests(unittest.TestCase):
    def test_area(self):
        self.assertEqual(s9._area_of("名古屋市南区鳥栖1丁目（緑支店=緑区鳴子町）"), "南区")
        self.assertEqual(s9._area_of("愛知県名古屋市天白区"), "天白区")
        self.assertEqual(s9._area_of("〒470-1103 愛知県豊明市沓掛町"), "豊明市")


class SendableFirstTests(unittest.TestCase):
    def test_next_pending_puts_email_and_form_first(self):
        import tempfile

        import yaml

        import jarvis_kurashift_mgmt_vendor_list as ml

        vendors = [
            {"id": "p1", "name": "電話A", "channel": "phone", "status": "pending", "property_lane": "midori_caramel"},
            {"id": "p2", "name": "電話B", "channel": "phone", "status": "pending", "property_lane": "midori_caramel"},
            {"id": "e1", "name": "メールC", "channel": "email", "status": "pending", "property_lane": "midori_caramel"},
        ]
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "list.yaml"
            p.write_text(yaml.safe_dump({"settings": {}, "vendors": vendors}, allow_unicode=True), encoding="utf-8")
            old = ml.LIST_PATH
            ml.LIST_PATH = p
            try:
                got = [v["id"] for v in ml.next_pending(limit=3, lane="midori_caramel")]
            finally:
                ml.LIST_PATH = old
        self.assertEqual(got, ["e1", "p1", "p2"])


if __name__ == "__main__":
    unittest.main()
