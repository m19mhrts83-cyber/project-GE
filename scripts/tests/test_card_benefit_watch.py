"""614 年間特典ウォッチ — 架空の値だけで検証（実額・実在の口座は使わない）。"""
import sys
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import jarvis_card_benefit_watch as c  # noqa: E402

CFG = {
    "pace": {"reach_ratio": 1.0, "tight_ratio": 1.5},
    "zaim_note": "概算",
    "cards": {
        "a": {
            "name": "カードA", "short": "A", "usage_source": "gmail_monthly",
            "period": {"type": "fixed", "start": "2026-01-01", "end": "2026-12-31"},
            "tiers": [
                {"id": "t1", "label": "下", "threshold_yen": 1_000_000,
                 "reward": "r1", "threshold_status": "estimated"},
                {"id": "t2", "label": "上", "threshold_yen": 3_000_000,
                 "reward": "r2", "threshold_status": "confirmed"},
            ],
        },
        "b": {
            "name": "カードB", "short": "B", "usage_source": "zaim_estimate",
            "period": {"type": "annual_from", "month": 3, "day": 1},
            "zaim_pay_contains": "FOO CARD", "zaim_exclude_keywords": ["年会費"],
            "tiers": [
                {"id": "t1", "label": "目標", "threshold_yen": 2_000_000,
                 "reward": "r", "threshold_status": "needs_check"},
            ],
        },
    },
    "olive_history": {"continuous": {"label": "継続", "period_start": "2026-01-01",
                                     "period_end": "2026-12-31", "grant_timing": "翌月末"}},
    "vpoint_exits": {"items": [
        {"label": "x", "status": "unconfirmed", "checked_on": "2026-01-01", "source": "s"},
        {"label": "投資", "status": "confirmed", "checked_on": "2026-01-01", "source": "s",
         "featured": True, "note": "注記", "extra_notes": ["追記"]},
    ]},
}


def st_a(usage, as_of="2026-07-01"):
    return {"olive": {"snapshots": [{"as_of": as_of, "usage_yen": usage}]}}


class PeriodTests(unittest.TestCase):
    def test_annual_from_before_and_after_start(self):
        cfg = CFG["cards"]["b"]
        self.assertEqual(c.period_for(cfg, date(2026, 11, 1)),
                         (date(2026, 3, 1), date(2027, 2, 28)))
        self.assertEqual(c.period_for(cfg, date(2027, 1, 10)),
                         (date(2026, 3, 1), date(2027, 2, 28)))
        self.assertEqual(c.period_for(cfg, date(2027, 3, 1))[0], date(2027, 3, 1))


class ComputeTests(unittest.TestCase):
    def test_achieved_tier_and_remaining(self):
        r = c.compute_card("a", CFG, st_a(1_200_000), date(2026, 7, 1))
        t1, t2 = r["tiers"]
        self.assertEqual(t1["verdict"], c.VERDICT_DONE)
        self.assertEqual(t1["remaining_yen"], 0)
        self.assertEqual(t2["remaining_yen"], 1_800_000)
        self.assertEqual(r["usage_kind"], "confirmed")

    def test_verdict_by_pace(self):
        # 6か月で120万 → 月約20万。残り約6か月。上の線は月30万必要 → 厳しい
        r = c.compute_card("a", CFG, st_a(1_200_000), date(2026, 7, 1))
        self.assertEqual(r["tiers"][1]["verdict"], c.VERDICT_TIGHT)
        # 月5万しか進まないなら届かない
        r2 = c.compute_card("a", CFG, st_a(300_000), date(2026, 7, 1))
        self.assertEqual(r2["tiers"][0]["verdict"], c.VERDICT_FAR)
        # 十分速ければ届く
        r3 = c.compute_card("a", CFG, st_a(2_500_000), date(2026, 7, 1))
        self.assertEqual(r3["tiers"][1]["verdict"], c.VERDICT_REACH)

    def test_period_ended_missed(self):
        r = c.compute_card("a", CFG, st_a(500_000, "2026-12-15"), date(2027, 1, 5))
        self.assertEqual(r["tiers"][0]["verdict"], c.VERDICT_MISSED)

    def test_no_data(self):
        r = c.compute_card("b", CFG, {}, date(2026, 7, 1))
        self.assertIsNone(r["usage_yen"])
        self.assertEqual(r["tiers"][0]["verdict"], c.VERDICT_NODATA)


class ZaimTests(unittest.TestCase):
    def test_aggregate_filters_pay_period_and_fee(self):
        index = {"updated_at": "x", "rows": {
            "1": {"date": "2026-04-01", "amount": 1000, "shop": "店", "item": "", "pay": "FOO CARD 本会員"},
            "2": {"date": "2026-05-01", "amount": 500, "shop": "店", "item": "", "pay": "BAR"},
            "3": {"date": "2026-03-20", "amount": 9000, "shop": "基本カード年会費", "item": "", "pay": "FOO CARD"},
            "4": {"date": "2025-12-01", "amount": 7000, "shop": "店", "item": "", "pay": "FOO CARD"},
            "5": {"date": "2026-06-10", "amount": 200, "shop": "店", "item": "", "pay": "foo card"},
        }}
        period = c.period_for(CFG["cards"]["b"], date(2026, 7, 1))
        agg = c.aggregate_zaim(index, CFG["cards"]["b"], period)
        self.assertEqual(agg["usage_yen"], 1200)
        self.assertEqual(agg["rows"], 2)
        self.assertEqual(agg["as_of"], "2026-06-10")

    def test_estimate_kind_has_caveat(self):
        state = {"bonvoy": {"zaim": {"usage_yen": 100000, "as_of": "2026-06-10"}}}
        r = c.compute_card("b", CFG, state, date(2026, 7, 1))
        self.assertEqual(r["usage_kind"], "estimate")
        self.assertTrue(r["usage_caveat"])


class MailParseTests(unittest.TestCase):
    def test_parse(self):
        body = "本メールでは、2026年3月15日現在のお客さま…\n\n 1,234,567円（税込）\n"
        self.assertEqual(c.parse_olive_mail(body), ("2026-03-15", 1_234_567))

    def test_parse_none(self):
        self.assertIsNone(c.parse_olive_mail("関係ない本文"))


class RecommendTests(unittest.TestCase):
    def test_prefers_reachable_and_cheaper(self):
        cards = [
            {"id": "a", "short": "A", "usage_yen": 1, "tiers": [
                {"label": "l", "verdict": c.VERDICT_TIGHT, "need_per_month_yen": 100}]},
            {"id": "b", "short": "B", "usage_yen": 1, "tiers": [
                {"label": "l", "verdict": c.VERDICT_REACH, "need_per_month_yen": 900}]},
        ]
        self.assertEqual(c.recommend(cards)["card"], "b")

    def test_none_reachable(self):
        cards = [{"id": "a", "short": "A", "usage_yen": 1, "tiers": [
            {"label": "l", "verdict": c.VERDICT_FAR, "need_per_month_yen": 1}]}]
        r = c.recommend(cards)
        self.assertIsNone(r["card"])
        self.assertIn("満足度", r["line"])

    def test_no_data(self):
        cards = [{"id": "a", "short": "A", "usage_yen": None, "tiers": []}]
        self.assertIsNone(c.recommend(cards)["card"])


class HistoryAndSlackTests(unittest.TestCase):
    def test_history_splits_done_and_upcoming(self):
        state = {"olive": {
            "grants": [{"label": "入会", "pt": 1, "status": "granted", "granted_on": "2026-02-01"},
                       {"label": "予定", "pt": 2, "status": "planned"}],
            "continuous_mail_status": {"as_of": "2026-06-15", "text": "進呈予定なし"}}}
        h = c.build_olive_history(CFG, state)
        self.assertEqual([g["label"] for g in h["achieved"]], ["入会"])
        self.assertEqual(h["upcoming"]["grant_timing"], "翌月末")
        self.assertEqual(h["upcoming"]["mail_status"]["text"], "進呈予定なし")

    def test_exits_keep_unconfirmed(self):
        items = c.build_vpoint_exits(CFG)["items"]
        self.assertEqual(items[0]["label"], "投資")  # featured が先頭
        self.assertTrue(items[0]["featured"])
        self.assertEqual(items[0]["extra_notes"], ["追記"])
        self.assertEqual(items[1]["status_label"], "未確認")

    def test_slack_text_shape_and_mask(self):
        state = st_a(1_200_000)
        res = c.compute(CFG, state, date(2026, 7, 1))
        text = c.build_slack_text(res, header="【見出し】", dash_url="https://example.invalid/x", mask=True)
        self.assertIn("今月はこちらを使うのがおすすめ", text.splitlines()[-1])
        self.assertNotIn("1,200,000", text)
        self.assertIn("A: ", text)
        self.assertIn("推定", text)  # 条件の確からしさを省かない


if __name__ == "__main__":
    unittest.main()
