#!/usr/bin/env python3
"""コミュニケーション台帳（comm hub）Phase 0/1 のテスト（ネットワーク不要）。"""
from __future__ import annotations

import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest import mock
from zoneinfo import ZoneInfo

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))

import jarvis_comm_hub as hub  # noqa: E402
import jarvis_gha_partner_triage as pt  # noqa: E402
from jarvis_night_triage import find_unreplied, parse_yoritoori_text  # noqa: E402

JST = ZoneInfo("Asia/Tokyo")


def _md(now: datetime) -> str:
    t1 = (now - timedelta(days=2)).strftime("%Y/%m/%d %H:%M")
    t2 = (now - timedelta(days=1)).strftime("%Y/%m/%d %H:%M")
    t3 = (now - timedelta(days=60)).strftime("%Y/%m/%d %H:%M")
    return f"""# ミニテック やり取りメモ

## やり取り（時系列）

### {t2}｜ミニテック｜相手から返信｜Re: 201号室 エアコン不具合

**件名**: Re: 201号室 エアコン不具合
松野様

お世話になっております。ミニテック林です。
エアコン交換の見積が届きました。ご確認ください。

---

### {t1}｜ミニテック｜自分から送信｜201号室 エアコン不具合

**件名**: 201号室 エアコン不具合
ミニテック
林 様

お世話になっております。松野です。
201号室のエアコンが故障しました。

---

### {t3}｜ミニテック｜相手から返信（Chatwork・管理G）｜定期清掃のご報告

清掃完了しました。
"""


class PartyTests(unittest.TestCase):
    def test_party_row_kind_and_must_check(self):
        row = hub.party_row(
            {
                "folder": "102_ミニテック",
                "name": "ミニテック",
                "emails": ["Hayashi@Minitech.co.jp"],
                "email_domains": ["minitech.co.jp"],
                "contact": "林",
            },
            now="2026-11-04T00:00:00+09:00",
        )
        assert row is not None
        self.assertEqual(row["party_id"], "partner:102_ミニテック")
        self.assertEqual(row["kind"], "mgmt")
        self.assertTrue(row["must_check"])
        self.assertEqual(row["emails"], ["hayashi@minitech.co.jp"])

    def test_kind_by_folder_prefix(self):
        self.assertEqual(hub.kind_for_folder("P806_神大家AI推進"), "club")
        self.assertEqual(hub.kind_for_folder("519_Kneesbee税理士法人"), "finance")
        self.assertEqual(hub.kind_for_folder("618_入居者"), "tenant")
        self.assertEqual(hub.kind_for_folder("misc"), "other")

    def test_folder_required(self):
        self.assertIsNone(hub.party_row({"name": "x"}, now=""))

    def test_repo_contact_yaml_loads(self):
        partners = hub.load_contact_partners(
            hub.REPO_PARTNER_BASE / "000_共通" / "連絡先一覧.yaml"
        )
        self.assertGreater(len(partners), 10)
        self.assertTrue(all(hub.party_row(p, now="") for p in partners if p.get("folder")))


class ItemTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime.now(JST)
        self.rows = hub.items_from_md_text(
            _md(self.now),
            "102_ミニテック",
            "ミニテック",
            recent_cutoff=self.now - timedelta(days=14),
        )
        self.by_subject = {r["subject"]: r for r in self.rows}

    def test_three_items(self):
        self.assertEqual(len(self.rows), 3)

    def test_inbound_recent_is_new(self):
        r = self.by_subject["Re: 201号室 エアコン不具合"]
        self.assertEqual(r["channel"], "gmail")
        self.assertEqual(r["direction"], "inbound")
        self.assertEqual(r["work_status"], "new")
        self.assertEqual(r["category"], "partner")
        self.assertEqual(r["ingest_status"], "ready")
        self.assertEqual(r["party_id"], "partner:102_ミニテック")
        self.assertIn("ミニテック｜102_ミニテック｜gmail｜相手→自分", r["context_header"])
        self.assertTrue(r["source_ref"]["path"].endswith("102_ミニテック/5.やり取り.md"))

    def test_outbound_is_done(self):
        r = self.by_subject["201号室 エアコン不具合"]
        self.assertEqual(r["direction"], "outbound")
        self.assertEqual(r["work_status"], "done")

    def test_old_chatwork_is_done(self):
        r = next(x for x in self.rows if x["channel"] == "chatwork")
        self.assertEqual(r["work_status"], "done")
        self.assertTrue(r["thread_key"].startswith("102_ミニテック|Chatwork|"))

    def test_self_reply_label_is_outbound(self):
        e = {
            "folder": "907_Raimo代理店",
            "partner_name": "Raimo",
            "received_at": "2026/10/01 10:00",
            "channel": "自分から返信",
            "summary": "s",
            "subject": "件名",
            "body": "本文",
        }
        self.assertEqual(hub.item_from_md_entry(e)["direction"], "outbound")

    def test_external_id_stable(self):
        again = hub.items_from_md_text(_md(self.now), "102_ミニテック", "ミニテック")
        self.assertEqual(
            sorted(r["external_id"] for r in self.rows),
            sorted(r["external_id"] for r in again),
        )

    def test_unparseable_date_skipped(self):
        self.assertIsNone(hub.item_from_md_entry({"received_at": "不明", "channel": ""}))

    def test_candidate_maps_to_same_dedupe_key(self):
        """111 の未返信候補から、同じ台帳行の dedupe_key が引けること。"""
        entries = parse_yoritoori_text(_md(self.now), "102_ミニテック", "ミニテック")
        cands = find_unreplied(entries, 14)
        self.assertEqual(len(cands), 1)
        c = cands[0]
        crow = hub.item_from_md_entry({**c, "channel": c.get("channel_raw") or c.get("channel")})
        target = self.by_subject["Re: 201号室 エアコン不具合"]
        self.assertEqual(hub.dedupe_key(crow), hub.dedupe_key(target))

    def test_double_entry_collapsed(self):
        """同日時・同本文で「自分から送信」と誤ラベルの「相手から返信」が並ぶ分は1行。"""
        body = "ミニテック 林 様\nお世話になっております。松野です。\n共用部アンペア変更の立ち会い完了のご連絡です。\n"
        md = (
            "### 2026/10/11 07:58｜ミニテック｜自分から送信｜アンペア変更\n\n**件名**: アンペア変更\n" + body + "\n---\n\n"
            "### 2026/10/11 07:58｜ミニテック｜相手から返信｜アンペア変更\n\n**件名**: アンペア変更\n" + body + "\n---\n"
        )
        rows = hub.items_from_md_text(md, "102_ミニテック", "ミニテック")
        self.assertEqual(len(rows), 1)

    def test_dedupe_key_ignores_timezone_format(self):
        a = {"party_id": "p", "channel": "gmail", "direction": "inbound",
             "occurred_at": "2026-10-11T07:58:00+09:00", "body_text": "本 文"}
        b = {**a, "occurred_at": "2026-10-10T22:58:00+00:00", "body_text": "本文"}
        self.assertEqual(hub.dedupe_key(a), hub.dedupe_key(b))

    def test_find_duplicate_ids_keeps_oldest(self):
        base = {"party_id": "p", "channel": "gmail", "direction": "outbound",
                "occurred_at": "2026-10-11T07:58:00+09:00", "body_text": "x"}
        rows = [
            {**base, "id": "b", "created_at": "2026-11-04T10:00:02+00:00"},
            {**base, "id": "a", "created_at": "2026-11-04T10:00:01+00:00"},
            {**base, "id": "c", "created_at": "2026-11-04T10:00:03+00:00", "body_text": "y"},
        ]
        self.assertEqual(hub.find_duplicate_ids(rows), ["b"])


class _Result:
    def __init__(self, data):
        self.data = data


class _Query:
    def __init__(self, db, table):
        self.db, self.table, self.op, self.payload, self.filters = db, table, None, None, []

    def select(self, *_a, **_k):
        self.op = "select"
        return self

    def upsert(self, rows, **kw):
        self.op, self.payload, self.kw = "upsert", rows, kw
        return self

    def update(self, values):
        self.op, self.payload = "update", values
        return self

    def in_(self, col, vals):
        self.filters.append(("in", col, list(vals)))
        return self

    def gte(self, col, val):
        self.filters.append(("gte", col, val))
        return self

    def order(self, *_a, **_k):
        return self

    def range(self, start, end):
        self.rng = (start, end)
        return self

    def delete(self):
        self.op = "delete"
        return self

    def eq(self, col, val):
        self.filters.append(("eq", col, val))
        return self

    def _match(self, row):
        for kind, col, val in self.filters:
            if kind == "in" and row.get(col) not in val:
                return False
            if kind == "eq" and row.get(col) != val:
                return False
            if kind == "gte" and str(row.get(col)) < str(val):
                return False
        return True

    def execute(self):
        rows = self.db.setdefault(self.table, [])
        if self.op == "upsert":
            for r in self.payload:
                if self.table == "comm_items":
                    key = (r["channel"], r["account"], r["external_id"])
                    if any((x["channel"], x["account"], x["external_id"]) == key for x in rows):
                        continue
                    r = {**r, "id": f"uuid-{len(rows) + 1}"}
                rows.append(dict(r))
            return _Result(self.payload)
        if self.op == "update":
            hit = [r for r in rows if self._match(r)]
            for r in hit:
                r.update(self.payload)
            return _Result(hit)
        if self.op == "delete":
            hit = [r for r in rows if self._match(r)]
            rows[:] = [r for r in rows if r not in hit]
            return _Result(hit)
        out = [r for r in rows if self._match(r)]
        if getattr(self, "rng", None):
            out = out[self.rng[0] : self.rng[1] + 1]
        return _Result(out)


class _FakeSB:
    def __init__(self):
        self.db: dict[str, list] = {}

    def table(self, name):
        return _Query(self.db, name)


class Phase1SyncTests(unittest.TestCase):
    def test_sync_links_and_marks_needs_reply(self):
        now = datetime.now(JST)
        entries = parse_yoritoori_text(_md(now), "102_ミニテック", "ミニテック")
        cands = find_unreplied(entries, 14)
        row = pt.row_from_candidate(cands[0], pt.heuristic_judge(cands[0]))
        assert row is not None
        sb = _FakeSB()
        with mock.patch.object(hub, "client", return_value=sb):
            n = pt.comm_hub_sync(entries, [(cands[0], row)], lookback_days=14)
        # 60日前の Chatwork は30日窓の外
        self.assertEqual(len(sb.db["comm_items"]), 2)
        self.assertEqual(n, 2)
        self.assertTrue(row["comm_item_id"].startswith("uuid-"))
        target = next(r for r in sb.db["comm_items"] if r["id"] == row["comm_item_id"])
        self.assertEqual(target["work_status"], "needs_reply")
        self.assertEqual(sb.db["comm_links"][0]["target_id"], row["id"])
        # 名簿にない party は自動で足される（FK 落ち防止）
        self.assertEqual(sb.db["comm_parties"][0]["party_id"], "partner:102_ミニテック")

    def test_second_run_keeps_closed_status(self):
        now = datetime.now(JST)
        entries = parse_yoritoori_text(_md(now), "102_ミニテック", "ミニテック")
        cands = find_unreplied(entries, 14)
        sb = _FakeSB()
        with mock.patch.object(hub, "client", return_value=sb):
            row = pt.row_from_candidate(cands[0], pt.heuristic_judge(cands[0]))
            pt.comm_hub_sync(entries, [(cands[0], row)], lookback_days=14)
            for r in sb.db["comm_items"]:
                if r["id"] == row["comm_item_id"]:
                    r["work_status"] = "done"  # 人が閉じた
            row2 = pt.row_from_candidate(cands[0], pt.heuristic_judge(cands[0]))
            pt.comm_hub_sync(entries, [(cands[0], row2)], lookback_days=14)
        self.assertEqual(len(sb.db["comm_items"]), 2)  # 重複しない
        target = next(r for r in sb.db["comm_items"] if r["id"] == row2["comm_item_id"])
        self.assertEqual(target["work_status"], "done")


class DedupeSyncTests(unittest.TestCase):
    def test_existing_variant_with_other_external_id_not_reinserted(self):
        now = datetime.now(JST)
        entries = parse_yoritoori_text(_md(now), "102_ミニテック", "ミニテック")
        cands = find_unreplied(entries, 14)
        row = pt.row_from_candidate(cands[0], pt.heuristic_judge(cands[0]))
        sb = _FakeSB()
        with mock.patch.object(hub, "client", return_value=sb):
            pt.comm_hub_sync(entries, [(cands[0], row)], lookback_days=14)
            before = len(sb.db["comm_items"])
            # DB 側の外部IDだけ別表記（二重記載の別見出し）にしても、新しい行は増えない
            for r in sb.db["comm_items"]:
                r["external_id"] = "md:other-" + r["external_id"]
                r["source_ref"] = {"source": "yoritoori_md"}
            row2 = pt.row_from_candidate(cands[0], pt.heuristic_judge(cands[0]))
            pt.comm_hub_sync(entries, [(cands[0], row2)], lookback_days=14)
        self.assertEqual(len(sb.db["comm_items"]), before)
        self.assertTrue(row2["comm_item_id"].startswith("uuid-"))


class MainSoftFailTests(unittest.TestCase):
    def test_comm_failure_does_not_block_push(self):
        now = datetime.now(JST)
        entries = parse_yoritoori_text(_md(now), "102_ミニテック", "ミニテック")

        def fake_cands(*, lookback_days, max_partners, collect=None):
            if collect is not None:
                collect.extend(entries)
            return find_unreplied(entries, lookback_days)

        pushed = {}

        def fake_push(rows):
            pushed["rows"] = rows
            return len(rows)

        with mock.patch.object(pt, "candidates_from_partners", fake_cands), mock.patch.object(
            pt, "push_rows", fake_push
        ), mock.patch.object(hub, "client", side_effect=RuntimeError("no tables")):
            rc = pt.main(["--push"])
        self.assertEqual(rc, 0)
        self.assertEqual(len(pushed["rows"]), 1)
        self.assertNotIn("comm_item_id", pushed["rows"][0])

    def test_disabled_by_flag(self):
        with mock.patch.object(pt, "candidates_from_partners", return_value=[]), mock.patch.object(
            pt, "push_rows", return_value=0
        ), mock.patch.object(pt, "comm_hub_sync") as sync:
            pt.main(["--push", "--no-comm-hub"])
        sync.assert_not_called()


if __name__ == "__main__":
    unittest.main()
