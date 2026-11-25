import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import jarvis_property_gate_lib as lib


def deal(grok, price=1000):
    return {"price_man": price, "summary_json": {"grok": grok}}


class RoutePriceTest(unittest.TestCase):
    def test_explanation_text_is_not_a_price(self):
        bad = [
            "（〇〇町は路線価図12345上「倍率地域」。周辺のみ10E〜20E等）",
            "（路線価地域なし・R08町丁索引に〇〇町なし）",
            "未確定（近傍公示系は約4.8〜6万/㎡…）",
            "（本件は調整区域。図1/2の路線10E〜20Eは別側）",
            "1,234円/㎡（30E・令和9・国税庁路線価図1）",
        ]
        for text in bad:
            self.assertIsNone(lib._route_price_tsubo_man(text), text)
            d = deal({"route_price_tsubo": text, "land_area": "100㎡",
                      "land100_ratio": "算定不可"})
            self.assertEqual(lib._land_display(d), ("", ""), text)
            lines = lib.land_eval_lines(d)
            self.assertIn("• 判定：材料不足（率・判定が無い）", lines)
            self.assertTrue(any("評価額：—" in x for x in lines))

    def test_clear_forms_still_work(self):
        self.assertEqual(lib._route_price_tsubo_man("35万/坪"), 35.0)
        self.assertEqual(lib._route_price_tsubo_man("参考20E≒約4.8万/坪相当"), 4.8)
        self.assertEqual(lib._route_price_tsubo_man("約4.8（50E=15,000円/㎡）"), 4.8)
        self.assertEqual(lib._route_price_tsubo_man("12.5"), 12.5)
        d = deal({"route_price_tsubo": "10万/坪", "land_area": "330.578㎡"})
        value_s, ratio_s = lib._land_display(d)
        self.assertEqual(value_s, "約1,000万")
        self.assertEqual(ratio_s, "100%")


class RatioTest(unittest.TestCase):
    def test_sentence_ratio_is_not_read(self):
        for text in ("算定不可", "未取得（…404…）", "不明（固評依頼要）"):
            self.assertEqual(lib._ratio_scenarios(text), [], text)
            self.assertEqual(lib._land_display(deal({"land100_ratio": text})),
                             ("", ""), text)

    def test_clear_ratio_unchanged(self):
        self.assertEqual(lib._land_display(deal({"land100_ratio": "123%"})),
                         ("約1,230万", "123%"))
        self.assertEqual(lib._ratio_scenarios("参考1.2（確定不可）"),
                         [(1.2, "確定不可")])

    def test_scenarios_unchanged(self):
        d = deal({"land_appraisal_man": "参考1,000（50E）／1,200（60E）"})
        value_s, ratio_s = lib._land_display(d)
        self.assertEqual(value_s, "約1,000万（50E）／約1,200万（60E）")
        self.assertEqual(ratio_s, "100%／120%")


if __name__ == "__main__":
    unittest.main()
