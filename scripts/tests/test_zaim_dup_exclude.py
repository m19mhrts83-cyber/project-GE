#!/usr/bin/env python3
"""Zaim 重複除外（型A/型B・画面の行特定・記録・Slack 文面）。架空の値だけ。ネットワーク・Playwright 不要。"""
from __future__ import annotations

import sys
import tempfile
import unittest
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, str(REPO / "215_kamiooya" / "C1_cursor" / "finance" / "zaim_budget_sync"))

import jarvis_zaim_dup_exclude as dup  # noqa: E402
import zaim_row_match as zm  # noqa: E402

INC = "常に集計に含める"
EXC = "集計に含めない"
CARD = "テストカードX"
CFG = {
    "include_label": INC,
    "exclude_label": EXC,
    "card_pay_keywords": ["テストカード"],
    "daily_shop_keywords": ["テスト商店"],
    "exclude_shop_keywords": ["ETC", "高速"],
}


def pay(date, amount, *, shop="テスト商店", card=CARD, item="", memo="", agg=INC, cat="食費"):
    return {
        "日付": date, "方法": "payment", "カテゴリ": cat, "支払元": card, "品目": item,
        "メモ": memo, "お店": shop, "支出": str(amount), "集計の設定": agg,
    }


def smart(date, amount, *, shop="テスト商店", agg=INC):
    return pay(date, amount, shop=shop, card="スマートレシート", agg=agg)


def web_row(price, *, calc=zm.CALC_INCLUDE, acct=CARD, place="テスト商店", name="", comment="", rid="100001"):
    return {"price": price, "calc": calc, "acct": acct, "place": place, "name": name,
            "comment": comment, "edit_url": f"/money/{rid}/edit"}


class RowMatchTests(unittest.TestCase):
    def test_price_is_exact_not_substring(self):
        self.assertTrue(zm.price_matches_exactly("¥1,000", 1000))
        self.assertFalse(zm.price_matches_exactly("¥11,000", 1000))
        self.assertFalse(zm.price_matches_exactly("¥1,000", 100))
        self.assertTrue(zm.price_matches_exactly("¥500", 500))
        self.assertFalse(zm.price_matches_exactly("¥1,500", 500))

    def test_edit_id_from_url(self):
        self.assertEqual(zm.edit_id_from_url("/money/123456/edit"), "123456")
        self.assertIsNone(zm.edit_id_from_url("/money/abc/edit"))
        self.assertIsNone(zm.edit_id_from_url(""))

    def test_type_a_pair_picks_card_row_by_account(self):
        rows = [web_row("¥1,234", acct="スマートレシート", rid="1"), web_row("¥1,234", rid="2")]
        row, why = zm.select_row(rows, amount=1234, pay=CARD, shop="テスト商店",
                                 expect_calc=zm.CALC_INCLUDE, group_size=1)
        self.assertEqual(why, "ok")
        self.assertEqual(zm.edit_id_from_url(row["edit_url"]), "2")

    def test_same_account_two_rows_stops_for_type_a(self):
        rows = [web_row("¥1,234", rid="1"), web_row("¥1,234", rid="2")]
        row, why = zm.select_row(rows, amount=1234, pay=CARD, shop="テスト商店",
                                 expect_calc=zm.CALC_INCLUDE, group_size=1)
        self.assertIsNone(row)
        self.assertIn(zm.R_GROUP_SIZE, why)

    def test_type_b_picks_the_empty_side(self):
        rows = [web_row("¥800", name="牛乳", rid="1"), web_row("¥800", rid="2")]
        row, why = zm.select_row(rows, amount=800, pay=CARD, shop="テスト商店",
                                 expect_calc=zm.CALC_INCLUDE, described=False, group_size=2)
        self.assertEqual(why, "ok")
        self.assertEqual(zm.edit_id_from_url(row["edit_url"]), "2")

    def test_type_b_both_empty_or_both_described_stops(self):
        for rows in (
            [web_row("¥800", rid="1"), web_row("¥800", rid="2")],
            [web_row("¥800", name="a", rid="1"), web_row("¥800", comment="b", rid="2")],
        ):
            row, why = zm.select_row(rows, amount=800, pay=CARD, shop="テスト商店",
                                     expect_calc=zm.CALC_INCLUDE, described=False, group_size=2)
            self.assertIsNone(row, why)

    def test_already_excluded_row_is_not_selected(self):
        rows = [web_row("¥1,234", calc=zm.CALC_EXCLUDE)]
        row, why = zm.select_row(rows, amount=1234, pay=CARD, expect_calc=zm.CALC_INCLUDE)
        self.assertIsNone(row)
        self.assertEqual(why, zm.R_CALC)

    def test_monthly_only_icon_is_not_standard(self):
        rows = [web_row("¥1,234", calc="add_circle")]
        row, _ = zm.select_row(rows, amount=1234, pay=CARD, expect_calc=zm.CALC_INCLUDE)
        self.assertIsNone(row)

    def test_account_and_shop_mismatch_stop(self):
        rows = [web_row("¥1,234", acct="別のカード")]
        self.assertEqual(zm.select_row(rows, amount=1234, pay=CARD)[1], zm.R_NO_ACCOUNT)
        rows = [web_row("¥1,234", place="別の店")]
        self.assertEqual(zm.select_row(rows, amount=1234, pay=CARD, shop="テスト商店")[1], zm.R_NO_SHOP)

    def test_truncated_pay_still_matches_and_no_rows(self):
        long_pay = "テストカードX" + "あ" * 50
        self.assertTrue(zm.account_matches(long_pay[:40], long_pay))
        self.assertEqual(zm.select_row([], amount=1)[1], zm.R_NO_PRICE)

    def test_modal_ready_requires_id_and_loaded_content(self):
        base = {"open": True, "spinner_visible": False, "content_children": 2,
                "form_actions": ["/receipts/555"]}
        self.assertTrue(zm.modal_ready(base, "555"))
        self.assertFalse(zm.modal_ready({**base, "spinner_visible": True}, "555"))
        self.assertFalse(zm.modal_ready({**base, "content_children": 0}, "555"))
        self.assertFalse(zm.modal_ready({**base, "form_actions": ["/receipts/999"]}, "555"))  # 前の明細の残り
        self.assertFalse(zm.modal_ready({"open": False}, "555"))
        self.assertFalse(zm.modal_ready(None, "555"))

    def test_verify_calc_by_id(self):
        rows = [web_row("¥1", calc=zm.CALC_EXCLUDE, rid="7"), web_row("¥1", rid="8")]
        self.assertEqual(zm.verify_calc(rows, "7", zm.CALC_EXCLUDE), (True, "ok"))
        self.assertFalse(zm.verify_calc(rows, "8", zm.CALC_EXCLUDE)[0])
        self.assertEqual(zm.verify_calc(rows, "9", zm.CALC_EXCLUDE), (False, zm.R_ID_NOT_FOUND))

    def test_agg_title_mapping(self):
        self.assertEqual(zm.agg_value_from_title("常に含める（標準）"), "10")
        self.assertEqual(zm.agg_value_from_title("常に含めない"), "0")
        self.assertIsNone(zm.agg_value_from_title("???"))


class CandidateTests(unittest.TestCase):
    def test_type_a_receipt_total_with_unique_card_row(self):
        pays = [smart("2026-01-10", 300), smart("2026-01-10", 700),
                pay("2026-01-10", 1000)]
        cands, skips = dup.find_candidates(pays, CFG)
        self.assertEqual([(c["type"], c["amount"]) for c in cands], [("A", 1000)])

    def test_type_a_skipped_when_card_row_not_unique(self):
        pays = [smart("2026-01-10", 1000), pay("2026-01-10", 1000), pay("2026-01-10", 1000)]
        cands, _ = dup.find_candidates(pays, CFG)
        self.assertEqual([c for c in cands if c["type"] == "A"], [])

    def test_type_a_skipped_when_card_already_excluded(self):
        pays = [smart("2026-01-10", 1000), pay("2026-01-10", 1000, agg=EXC)]
        cands, _ = dup.find_candidates(pays, CFG)
        self.assertEqual(cands, [])

    def test_type_b_picks_empty_side(self):
        pays = [pay("2026-02-01", 400, item="お茶"), pay("2026-02-01", 400)]
        cands, _ = dup.find_candidates(pays, CFG)
        self.assertEqual(len(cands), 1)
        c = cands[0]
        self.assertEqual((c["type"], c["item"], c["memo"]), ("B", "", ""))
        act = dup.web_action(c)
        self.assertEqual((act["group_size"], act["described"], act["value"]), (2, False, "exclude"))

    def test_type_b_memo_counts_as_description(self):
        pays = [pay("2026-02-01", 400, memo="メモあり"), pay("2026-02-01", 400)]
        cands, _ = dup.find_candidates(pays, CFG)
        self.assertEqual(len(cands), 1)

    def test_type_b_exclusions(self):
        cases = {
            "3行以上": [pay("2026-02-01", 400, item="a"), pay("2026-02-01", 400), pay("2026-02-01", 400)],
            "どちらも記述なし": [pay("2026-02-01", 400), pay("2026-02-01", 400)],
            "どちらも記述あり": [pay("2026-02-01", 400, item="a"), pay("2026-02-01", 400, memo="b")],
            "すでに除外済み": [pay("2026-02-01", 400, item="a"), pay("2026-02-01", 400, agg=EXC)],
            "逆向き": [pay("2026-02-01", 400, item="a", agg=EXC), pay("2026-02-01", 400)],
            "高速": [pay("2026-02-01", 400, item="a", shop="高速道路"), pay("2026-02-01", 400, shop="高速道路")],
            "交通カテゴリ": [pay("2026-02-01", 400, item="a", cat="交通費"), pay("2026-02-01", 400, cat="交通費")],
            "お店が違う": [pay("2026-02-01", 400, item="a"), pay("2026-02-01", 400, shop="全然別の店")],
            "違うカード": [pay("2026-02-01", 400, item="a"), pay("2026-02-01", 400, card="テストカードY")],
            "別の日": [pay("2026-02-01", 400, item="a"), pay("2026-02-02", 400)],
            "別の額": [pay("2026-02-01", 400, item="a"), pay("2026-02-01", 401)],
        }
        for name, pays in cases.items():
            cands, _ = dup.find_candidates(pays, CFG)
            self.assertEqual(cands, [], name)

    def test_smart_receipt_pairs_are_never_type_b(self):
        pays = [smart("2026-02-01", 400), smart("2026-02-01", 400)]
        cands, _ = dup.find_candidates(pays, CFG)
        self.assertEqual(cands, [])

    def test_newest_first_ordering(self):
        pays = [pay("2026-02-01", 400, item="a"), pay("2026-02-01", 400),
                pay("2026-03-05", 500, item="a"), pay("2026-03-05", 500)]
        cands, _ = dup.find_candidates(pays, CFG)
        self.assertEqual([c["date"] for c in cands], ["2026-03-05", "2026-02-01"])


class RecordTests(unittest.TestCase):
    def test_classify_existing(self):
        self.assertEqual(dup.classify_existing(None, retry_manual=False), "new")
        self.assertEqual(dup.classify_existing({"status": dup.ST_EXCLUDED}, retry_manual=False), "skip")
        self.assertEqual(dup.classify_existing({"status": dup.ST_REVERTED}, retry_manual=True), "skip")
        self.assertEqual(dup.classify_existing({"status": dup.ST_MANUAL}, retry_manual=False), "skip")
        self.assertEqual(dup.classify_existing({"status": dup.ST_MANUAL}, retry_manual=True), "retry")
        self.assertEqual(dup.classify_existing({"status": dup.ST_FAILED}, retry_manual=False), "retry")

    def test_save_and_upsert_roundtrip(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "rec.json"
            rec = dup.load_record(path)
            self.assertEqual(rec["entries"], [])
            dup._upsert(rec, {"cand_key": "k", "status": dup.ST_FAILED, "attempts": 1})
            dup._upsert(rec, {"cand_key": "k", "status": dup.ST_EXCLUDED, "zaim_id": "42"})
            dup.save_record(rec, path)
            again = dup.load_record(path)
            self.assertEqual(len(again["entries"]), 1)
            self.assertEqual(again["entries"][0]["zaim_id"], "42")
            self.assertEqual(again["entries"][0]["attempts"], 1)  # 既存項目は上書きされず残る

    def test_revert_targets_by_id_and_run(self):
        rec = {"entries": [
            {"zaim_id": "1", "run_id": "r1", "status": dup.ST_EXCLUDED},
            {"zaim_id": "2", "run_id": "r1", "status": dup.ST_REVERTED},
            {"zaim_id": "3", "run_id": "r2", "status": dup.ST_EXCLUDED},
        ]}
        self.assertEqual([e["zaim_id"] for e in dup.pick_revert_targets(rec, ["3"], [])], ["3"])
        self.assertEqual([e["zaim_id"] for e in dup.pick_revert_targets(rec, [], ["r1"])], ["1"])


class FakeEdit:
    """画面操作の代役。特定→変更→確認の流れと3回失敗で要手動になることを確かめる。"""

    def __init__(self, *, locate_ok=True, change_ok=True):
        self.locate_ok, self.change_ok = locate_ok, change_ok
        self.changes = 0

    def verify_by_id(self, page, day, amount, zid, calc):
        return False, "x"

    def locate_target(self, page, action):
        if not self.locate_ok:
            return None, zm.R_GROUP_SIZE + "（2件）"
        return web_row(f"¥{action['amount']:,}", rid="4242") | {"calc_title": "常に含める（標準）"}, "ok"

    def change_aggregate_by_id(self, page, **kw):
        self.changes += 1
        if self.change_ok:
            return {"ok": True, "message": "ok", "zaim_id": kw["zaim_id"], "prev_agg": "10", "verified": True}
        return {"ok": False, "message": "保存後の確認で反映を確認できない", "zaim_id": kw["zaim_id"],
                "prev_agg": "10", "verified": False}


def run(fake, *, apply, cands=None, rec=None, max_apply=5):
    cands = cands if cands is not None else [dup._candidate("B", pay("2026-02-01", 400))]
    rec = rec if rec is not None else {"entries": []}
    orig = dup.save_record
    dup.save_record = lambda *a, **k: None  # テストでは書かない
    orig_sleep = dup.time.sleep
    dup.time.sleep = lambda *_: None
    try:
        return dup.process_candidates(cands, rec, apply=apply, run_id="dup-test", max_apply=max_apply,
                                      scan=25, retry_manual=False, zedit=fake, page=None), rec
    finally:
        dup.save_record = orig
        dup.time.sleep = orig_sleep


class ProcessTests(unittest.TestCase):
    def test_dry_run_changes_nothing_and_writes_nothing(self):
        fake = FakeEdit()
        (results, manual, unmatched), rec = run(fake, apply=False)
        self.assertEqual(fake.changes, 0)
        self.assertEqual(results[0]["state"], "identified")
        self.assertEqual(rec["entries"], [])

    def test_apply_records_everything_needed(self):
        fake = FakeEdit()
        (results, manual, unmatched), rec = run(fake, apply=True)
        e = rec["entries"][0]
        self.assertEqual(e["status"], dup.ST_EXCLUDED)
        for k in ("date", "amount", "shop", "card", "type", "zaim_id", "prev_agg", "executed_at", "run_id", "verification"):
            self.assertIn(k, e)
        self.assertEqual((e["zaim_id"], e["prev_agg"], e["run_id"], e["verified"]), ("4242", "10", "dup-test", True))

    def test_unmatched_is_not_applied_and_not_recorded(self):
        fake = FakeEdit(locate_ok=False)
        (results, manual, unmatched), rec = run(fake, apply=True)
        self.assertEqual(fake.changes, 0)
        self.assertEqual(rec["entries"], [])
        self.assertEqual(sum(unmatched.values()), 1)

    def test_three_failures_become_manual_required(self):
        fake = FakeEdit(change_ok=False)
        (results, manual, unmatched), rec = run(fake, apply=True)
        self.assertEqual(fake.changes, dup.MAX_ATTEMPTS)
        self.assertEqual(rec["entries"][0]["status"], dup.ST_MANUAL)
        self.assertEqual(len(manual), 1)

    def test_cap_per_run(self):
        fake = FakeEdit()
        cands = [dup._candidate("B", pay(f"2026-02-{d:02d}", 400)) for d in range(1, 9)]
        (results, manual, unmatched), rec = run(fake, apply=True, cands=cands, max_apply=5)
        self.assertEqual(fake.changes, 5)
        self.assertEqual(len(rec["entries"]), 5)

    def test_previously_excluded_or_reverted_are_skipped(self):
        c = dup._candidate("B", pay("2026-02-01", 400))
        for st in (dup.ST_EXCLUDED, dup.ST_REVERTED):
            fake = FakeEdit()
            rec = {"entries": [{"cand_key": dup.cand_key(c), "status": st}]}
            run(fake, apply=True, cands=[c], rec=rec)
            self.assertEqual(fake.changes, 0)


class SlackTextTests(unittest.TestCase):
    def test_report_text_format(self):
        ents = [{"status": dup.ST_EXCLUDED, "type": "A", "amount": 1000},
                {"status": dup.ST_EXCLUDED, "type": "B", "amount": 234},
                {"status": dup.ST_FAILED, "type": "B", "amount": 99}]
        t = dup.build_report_text(ents, "dup-1")
        self.assertIn("重複除外 2件(型A 1・型B 1)", t)
        self.assertIn("計 ¥1,234", t)
        self.assertIn("戻すのは", t)
        self.assertIn("dup-1", t)

    def test_no_report_when_nothing_excluded(self):
        self.assertIsNone(dup.build_report_text([{"status": dup.ST_FAILED}], "r"))

    def test_ops_text_only_when_manual(self):
        self.assertIsNone(dup.build_ops_text([], "r"))
        t = dup.build_ops_text([{"date": "2026-02-01", "amount": 400, "type": "B", "last_message": "x"}], "r")
        self.assertIn("要手動", t)


class CliSafetyTests(unittest.TestCase):
    def test_apply_requires_yes_and_default_is_dry_run(self):
        self.assertEqual(dup.main(["--apply"]), 1)

    def test_max_is_capped(self):
        self.assertEqual(dup.MAX_PER_RUN, 5)


if __name__ == "__main__":
    unittest.main()
