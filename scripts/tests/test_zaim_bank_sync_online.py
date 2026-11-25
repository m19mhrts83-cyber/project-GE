#!/usr/bin/env python3
"""Zaim 銀行連携ウォッチ: 「Zaim の更新日時」も見る判定。架空の値だけ。ネットワーク・Playwright 不要。"""
from __future__ import annotations

import csv
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))

import jarvis_zaim_bank_sync_check as chk  # noqa: E402
import jarvis_zaim_online_accounts as zo  # noqa: E402

JST = zo.JST
FETCHED = datetime(2026, 12, 1, 9, 0, 0, tzinfo=JST)


def _row(group: str, website: str, account: str, updated: str, *, notice="", caution="", faq="") -> str:
    parts = ['<tr><td class="OnlineAccountSummary-module__name___aaa"><div>']
    if faq:
        parts.append(f'<a class="OnlineAccountSummary-module__faqLink___bbb"><i>help_outline</i>{faq}</a>')
    if notice:
        parts.append(
            '<div class="OnlineAccountSummary-module__onlineAccountNotice___ccc">'
            f'<div class="OnlineAccountSummary-module__textNotice___ddd">{notice}</div></div>'
        )
    parts.append(f'<div class="OnlineAccountSummary-module__websiteName___eee">{website}</div>')
    if account:
        parts.append(f'<div class="OnlineAccountSummary-module__accountName___fff">{account}</div>')
    if caution:
        parts.append(f'<div class="OnlineAccountSummary-module__caution___ggg">{caution}</div>')
    parts.append(f'<div class="OnlineAccountSummary-module__textMuted___hhh">{updated}</div></div>')
    # 押す操作のメニュー（読み取りでは使わない）
    parts.append('<div><ul><li><div>連携データを更新</div></li></ul></div></td></tr>')
    return "".join(parts)


def _bar(title: str) -> str:
    return (
        '<div class="OnlineAccountStatusBar-module__bar___iii"><div class="OnlineAccountStatusBar-module__mark___jjj">●</div>'
        f'<div class="OnlineAccountStatusBar-module__title___kkk">{title}</div></div>'
    )


FIXTURE = (
    "<html><body>"
    + _bar("更新再開の操作待ち")
    + "<table><tbody>"
    + _row("g", "テスト銀行A", "テスト銀行A 本店 普通 ****1", "最終更新：2026年09月13日 09:28:49",
           notice="ログインの有効期限が切れました。連携設定よりログイン情報の修正をお願いします。", faq="連携できない")
    + "</tbody></table>"
    + _bar("自分で更新")
    + "<table><tbody>"
    + _row("g", "テストペイ", "テストペイ 太郎", "最終更新：2026年10月02日 09:20:51（自動取得非対応）")
    + "</tbody></table>"
    + _bar("3日以内に更新予定")
    + "<table><tbody>"
    + _row("g", "テスト銀行B", "★テスト銀行B 支店 普通預金 ***2", "最終更新：2026年11月30日 09:51:49")
    + _row("g", "テスト銀行C", "★テスト銀行C 支店", "最終更新：2026年11月21日 07:34:45", caution="定期更新のみ")
    + _row("g", "テストカード", "", "最終更新：2026年11月29日 10:00:00")
    + "</tbody></table>"
    + "</body></html>"
)


class ParseTests(unittest.TestCase):
    def setUp(self):
        self.rows = zo.parse_online_accounts_html(FIXTURE)
        self.by = {r["website"]: r for r in self.rows}

    def test_all_rows_read_with_group(self):
        self.assertEqual(len(self.rows), 5)
        self.assertEqual(self.by["テスト銀行A"]["group"], "更新再開の操作待ち")
        self.assertEqual(self.by["テストペイ"]["group"], "自分で更新")
        self.assertEqual(self.by["テスト銀行B"]["group"], "3日以内に更新予定")

    def test_updated_time_is_jst_iso(self):
        self.assertEqual(self.by["テスト銀行B"]["last_updated"], "2026-11-30T09:51:49+0900")

    def test_notice_and_broken_link(self):
        a = self.by["テスト銀行A"]
        self.assertIn("ログインの有効期限", a["notice"])
        self.assertTrue(a["link_broken"])
        self.assertTrue(zo.has_zaim_error(a))
        self.assertIsNone(self.by["テスト銀行B"]["notice"])
        self.assertFalse(zo.has_zaim_error(self.by["テスト銀行B"]))

    def test_flags(self):
        self.assertTrue(self.by["テストペイ"]["auto_unsupported"])
        self.assertTrue(self.by["テスト銀行C"]["periodic_only"])
        self.assertFalse(self.by["テスト銀行B"]["periodic_only"])
        self.assertEqual(self.by["テストカード"]["account"], "")

    def test_update_menu_text_is_not_mistaken_for_data(self):
        self.assertNotIn("連携データを更新", " ".join(str(v) for r in self.rows for v in r.values()))

    def test_unreadable_page_gives_empty(self):
        self.assertEqual(zo.parse_online_accounts_html("<html><body>ログイン</body></html>"), [])
        self.assertEqual(zo.build_snapshot([])["status"], "parse_empty")

    def test_updated_time_without_seconds_and_garbage(self):
        self.assertEqual(zo.parse_updated("最終更新：2026年1月5日 9:05")[0], "2026-01-05T09:05:00+0900")
        self.assertEqual(zo.parse_updated("更新なし"), (None, False))


class MatchTests(unittest.TestCase):
    def setUp(self):
        self.rows = zo.parse_online_accounts_html(FIXTURE)

    def test_star_and_spaces_ignored(self):
        self.assertEqual(zo.match_online_account("★テスト銀行B", self.rows)["website"], "テスト銀行B")
        self.assertEqual(zo.match_online_account("テスト 銀行 B", self.rows)["website"], "テスト銀行B")

    def test_matches_service_name_when_account_name_empty(self):
        self.assertEqual(zo.match_online_account("テストカード", self.rows)["website"], "テストカード")

    def test_list_of_needles_and_not_found(self):
        self.assertEqual(zo.match_online_account(["存在しない", "テスト銀行C"], self.rows)["website"], "テスト銀行C")
        self.assertIsNone(zo.match_online_account("存在しない", self.rows))
        self.assertIsNone(zo.match_online_account("", self.rows))


def online(**kw):
    base = {"last_updated": "2026-11-30T09:00:00+0900", "notice": None, "link_broken": False, "group": "3日以内に更新予定"}
    base.update(kw)
    return base


class JudgeTests(unittest.TestCase):
    def test_a_alive_even_if_last_transaction_is_old(self):
        stale, state, extra = chk.judge_sync(True, online(), 14, FETCHED)
        self.assertFalse(stale)
        self.assertEqual(state, chk.SYNC_ALIVE_NO_TXN)
        self.assertEqual(extra["zaim_update_age_days"], 1.0)

    def test_a_alive_with_recent_transaction(self):
        stale, state, _ = chk.judge_sync(False, online(), 14, FETCHED)
        self.assertFalse(stale)
        self.assertEqual(state, chk.SYNC_ALIVE)

    def test_b_old_update_is_stale(self):
        stale, state, _ = chk.judge_sync(True, online(last_updated="2026-11-10T09:00:00+0900"), 14, FETCHED)
        self.assertTrue(stale)
        self.assertEqual(state, chk.SYNC_STOPPED)

    def test_b_old_update_is_stale_even_if_csv_is_fresh(self):
        stale, state, _ = chk.judge_sync(False, online(last_updated="2026-11-10T09:00:00+0900"), 14, FETCHED)
        self.assertTrue(stale)
        self.assertEqual(state, chk.SYNC_STOPPED)

    def test_b_threshold_boundary_is_stale_like_csv_rule(self):
        stale, _, _ = chk.judge_sync(True, online(last_updated="2026-11-17T09:00:00+0900"), 14, FETCHED)
        self.assertTrue(stale)  # ちょうど14日 → 従来の「閾値以上は遅れ」と同じ
        stale, _, _ = chk.judge_sync(True, online(last_updated="2026-11-18T09:00:00+0900"), 14, FETCHED)
        self.assertFalse(stale)

    def test_b_error_display_wins_over_fresh_update(self):
        stale, state, extra = chk.judge_sync(
            False, online(notice="ログインの有効期限が切れました", link_broken=True), 14, FETCHED
        )
        self.assertTrue(stale)
        self.assertEqual(state, chk.SYNC_NEEDS_REAUTH)
        self.assertIn("ログイン", extra["zaim_notice"])

    def test_b_other_error_is_sync_error(self):
        stale, state, _ = chk.judge_sync(False, online(notice="メンテナンス中です"), 14, FETCHED)
        self.assertTrue(stale)
        self.assertEqual(state, chk.SYNC_ERROR)

    def test_b_waiting_group_counts_as_error(self):
        stale, state, _ = chk.judge_sync(False, online(group="更新再開の操作待ち"), 14, FETCHED)
        self.assertTrue(stale)
        self.assertEqual(state, chk.SYNC_NEEDS_REAUTH)

    def test_c_no_online_info_falls_back_to_csv(self):
        for csv_stale in (True, False):
            stale, state, extra = chk.judge_sync(csv_stale, None, 14, FETCHED)
            self.assertEqual(stale, csv_stale)
            self.assertEqual(state, chk.SYNC_UNVERIFIED)
            self.assertEqual(extra, {})

    def test_c_unreadable_time_or_no_fetch_time_falls_back(self):
        self.assertEqual(chk.judge_sync(True, online(last_updated=None), 14, FETCHED)[1], chk.SYNC_UNVERIFIED)
        self.assertEqual(chk.judge_sync(True, online(), 14, None)[1], chk.SYNC_UNVERIFIED)


class SnapshotTests(unittest.TestCase):
    def snap(self, **kw):
        base = {"status": "ok", "fetched_at": "2026-11-28T09:00:00+0900", "accounts": []}
        base.update(kw)
        return base

    def test_usable_within_age(self):
        ok, _ = zo.snapshot_usable(self.snap(), max_age_days=5, now=FETCHED)
        self.assertTrue(ok)

    def test_too_old_or_failed_or_missing(self):
        self.assertFalse(zo.snapshot_usable(self.snap(fetched_at="2026-11-20T09:00:00+0900"), max_age_days=5, now=FETCHED)[0])
        self.assertFalse(zo.snapshot_usable(self.snap(status="auth_blocked"), max_age_days=5, now=FETCHED)[0])
        self.assertFalse(zo.snapshot_usable({}, max_age_days=5, now=FETCHED)[0])
        self.assertFalse(zo.snapshot_usable(self.snap(fetched_at="???"), max_age_days=5, now=FETCHED)[0])


class EvaluateTests(unittest.TestCase):
    """CSV（架空）＋スナップショットで evaluate 全体を通す。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name) / "2026年度"
        base.mkdir()
        with (base / "Zaim.2026年度.csv").open("w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["日付", "支払元", "入金先"])
            w.writeheader()
            w.writerow({"日付": "2026-11-30", "支払元": "★テスト銀行B", "入金先": "-"})  # 取引なしではない
            w.writerow({"日付": "2026-11-09", "支払元": "-", "入金先": "★テスト銀行C"})  # 取引が古い
            w.writerow({"日付": "2026-11-09", "支払元": "-", "入金先": "★テスト銀行D"})  # 取引が古い・画面に無い
            w.writerow({"日付": "2026-11-09", "支払元": "-", "入金先": "★テスト銀行E"})  # 取引が古い・エラー表示
        self.cfg = {
            "csv_base_dir": self.tmp.name,
            "default_stale_days": 14,
            "accounts": [
                {"id": "b", "label": "銀行B", "match": "★テスト銀行B"},
                {"id": "c", "label": "銀行C", "match": "★テスト銀行C"},
                {"id": "d", "label": "銀行D", "match": "★テスト銀行D"},
                {"id": "e", "label": "銀行E", "match": "★テスト銀行E"},
            ],
        }
        rows = zo.parse_online_accounts_html(
            _bar("3日以内に更新予定")
            + "<table><tbody>"
            + _row("g", "テスト銀行B", "★テスト銀行B", "最終更新：2026年11月30日 09:00:00")
            + _row("g", "テスト銀行C", "★テスト銀行C", "最終更新：2026年11月30日 08:00:00")
            + _row("g", "テスト銀行E", "★テスト銀行E", "最終更新：2026年11月30日 08:00:00",
                   notice="ログインの有効期限が切れました", faq="連携できない")
            + "</tbody></table>"
        )
        self.online = (rows, FETCHED, {"status": "ok", "fetched_at": FETCHED.isoformat()})

    def tearDown(self):
        self.tmp.cleanup()

    def states(self, res):
        return {r["id"]: (r["status"], r["sync_state"]) for k in ("stale", "ok") for r in res[k]}

    def test_with_online_info(self):
        res = chk.evaluate(self.cfg, 2026, self.online)
        st = self.states(res)
        self.assertEqual(st["b"], ("ok", chk.SYNC_ALIVE))
        self.assertEqual(st["c"], ("ok", chk.SYNC_ALIVE_NO_TXN))  # 取引が古いだけ → 遅れ扱いにしない
        self.assertEqual(st["d"], ("stale", chk.SYNC_UNVERIFIED))  # 画面に無い → 従来の CSV 判定
        self.assertEqual(st["e"], ("stale", chk.SYNC_NEEDS_REAUTH))
        self.assertEqual([r["id"] for r in res["alive_no_txn"]], ["c"])
        self.assertIn("取引なし・連携OK 1件", res["summary"])
        self.assertIn("更新日時未確認 1件", res["summary"])
        self.assertIn("確かめられなかった", res["detail"])
        self.assertEqual(res["online_check"]["status"], "ok")
        self.assertEqual(res["level"], "attention")

    def test_without_online_info_is_old_behaviour(self):
        res = chk.evaluate(self.cfg, 2026, ([], None, {"status": "unavailable", "reason": "未取得"}))
        st = self.states(res)
        self.assertEqual(st["b"], ("ok", chk.SYNC_UNVERIFIED))
        for aid in ("c", "d", "e"):
            self.assertEqual(st[aid], ("stale", chk.SYNC_UNVERIFIED))
        self.assertEqual(res["alive_no_txn"], [])
        self.assertIn("更新日時は確認できず", res["summary"])
        self.assertIn("更新日時は確かめられなかった（未取得）", res["detail"])

    def test_online_match_overrides_match(self):
        self.cfg["accounts"][2]["online_match"] = ["テスト銀行C"]  # D を画面上の別名 C に結びつける
        res = chk.evaluate(self.cfg, 2026, self.online)
        self.assertEqual(self.states(res)["d"], ("ok", chk.SYNC_ALIVE_NO_TXN))


if __name__ == "__main__":
    unittest.main()
