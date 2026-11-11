#!/usr/bin/env python3
"""受付の表（comm_intake）→ 台帳の取り込みと、Grok 部長メールの中継のテスト（ネットワーク不要）。"""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import jarvis_comm_hub as hub  # noqa: E402
from test_comm_hub import _FakeSB  # noqa: E402


def intake(i: str, **p) -> dict:
    base = {
        "kind": "property",
        "occurred_at": "2026-11-10T23:30:00.000Z",
        "title": "東郷町 戸建て 新着",
        "summary": "要確認",
        "refs": {},
        "source": "Grok部長日報",
    }
    base.update(p)
    return {"id": f"in-{i}", "source_bot": "grok", "bot_item_id": i, "payload": base, "status": "new", "received_at": f"2026-11-11T00:00:0{i[-1]}Z"}


PARTIES = {"partner:102_ミニテック": "partner:102_ミニテック", "folder:102_ミニテック": "partner:102_ミニテック", "name:ミニテック": "partner:102_ミニテック"}


class IntakeToItemTests(unittest.TestCase):
    def test_property_maps(self):
        item, why = hub.intake_to_item(intake("a1"), PARTIES)
        self.assertIsNone(why)
        self.assertEqual(item["external_id"], "intake:grok:a1")
        self.assertEqual(item["category"], "property")
        self.assertEqual(item["channel"], "other")
        self.assertEqual(item["account"], "bot:grok")
        self.assertEqual(item["work_status"], "new")
        self.assertEqual(item["direction"], "inbound")
        self.assertIsNone(item["party_id"])
        self.assertIn("kind:property", item["tags"])

    def test_party_match_by_folder_or_name(self):
        item, _ = hub.intake_to_item(intake("a2", kind="partner", refs={"partner_folder": "102_ミニテック"}), PARTIES)
        self.assertEqual(item["party_id"], "partner:102_ミニテック")
        item, _ = hub.intake_to_item(intake("a3", kind="partner", refs={"partner": "ミニテック"}), PARTIES)
        self.assertEqual(item["party_id"], "partner:102_ミニテック")
        item, _ = hub.intake_to_item(intake("a4", kind="partner", refs={"partner": "知らない会社"}), PARTIES)
        self.assertIsNone(item["party_id"])

    def test_agent_report_is_no_action(self):
        item, _ = hub.intake_to_item(intake("a5", kind="agent"), PARTIES)
        self.assertEqual(item["category"], "agent")
        self.assertEqual(item["work_status"], "no_action")

    def test_topic_decides_action_for_agent(self):
        # 修繕候補・開発カードは agent でも「やること」
        for t in ("repair_vendor", "dev_card"):
            item, _ = hub.intake_to_item(intake(f"t-{t}", kind="agent", topic=t), PARTIES)
            self.assertEqual(item["work_status"], "new", t)
            self.assertIn(f"topic:{t}", item["tags"])
            self.assertEqual(item["payload"]["topic"], t)
            self.assertTrue(item["thread_key"].endswith(f"|{t}"))
        # 日報は知らせだけ
        item, _ = hub.intake_to_item(intake("t-d", kind="agent", topic="daily_report"), PARTIES)
        self.assertEqual(item["work_status"], "no_action")
        # needs_action で個別に上書き
        item, _ = hub.intake_to_item(intake("t-n1", kind="agent", topic="daily_report", needs_action=True), PARTIES)
        self.assertEqual(item["work_status"], "new")
        item, _ = hub.intake_to_item(intake("t-n2", kind="property", topic="property_research", needs_action=False), PARTIES)
        self.assertEqual(item["work_status"], "no_action")
        # 形が崩れた topic は無視（tag にも出さない）
        item, _ = hub.intake_to_item(intake("t-x", kind="agent", topic="Bad Topic!"), PARTIES)
        self.assertEqual(item["work_status"], "no_action")
        self.assertFalse(any(t.startswith("topic:") for t in item["tags"]))

    def test_gate_rejects(self):
        for p, frag in [
            ({"kind": "skim"}, "skim"),
            ({"kind": "bank"}, "kind"),
            ({"title": ""}, "title"),
            ({"title": "【認証コード】123456"}, "銀行・認証"),
            ({"summary": "三井住友銀行 振込のお知らせ"}, "銀行・認証"),
            ({"occurred_at": "昨日"}, "occurred_at"),
        ]:
            item, why = hub.intake_to_item(intake("b1", **p), PARTIES)
            self.assertIsNone(item, p)
            self.assertIn(frag, why)


class IngestIntakeTests(unittest.TestCase):
    def _sb(self):
        sb = _FakeSB()
        sb.db["comm_parties"] = [{"party_id": "partner:102_ミニテック", "name": "ミニテック", "partner_folder": "102_ミニテック"}]
        sb.db["comm_intake"] = [
            intake("c1"),
            intake("c2", kind="partner", refs={"partner_folder": "102_ミニテック"}),
            intake("c3", kind="skim"),
            {**intake("c4"), "status": "ingested"},
        ]
        return sb

    def test_dry_run_writes_nothing(self):
        sb = self._sb()
        st = hub.ingest_intake(sb, apply=False)
        self.assertEqual((st["new"], st["ingested"], st["rejected"]), (3, 2, 1))
        self.assertNotIn("comm_items", sb.db)
        self.assertEqual([r["status"] for r in sb.db["comm_intake"]], ["new", "new", "new", "ingested"])

    def test_apply_ingests_and_marks(self):
        sb = self._sb()
        hub.ingest_intake(sb, apply=True)
        self.assertEqual(sorted(r["external_id"] for r in sb.db["comm_items"]), ["intake:grok:c1", "intake:grok:c2"])
        st = {r["bot_item_id"]: r for r in sb.db["comm_intake"]}
        self.assertEqual(st["c1"]["status"], "ingested")
        self.assertTrue(st["c1"]["ingested_item_id"].startswith("uuid-"))
        self.assertEqual(st["c3"]["status"], "rejected")
        self.assertIn("skim", st["c3"]["error"])
        # 2回目は new が無いので何もしない（冪等）
        again = hub.ingest_intake(sb, apply=True)
        self.assertEqual(again["new"], 0)
        self.assertEqual(len(sb.db["comm_items"]), 2)

    def test_cli_soft_fails(self):
        with mock.patch.object(hub, "client", side_effect=RuntimeError("down")):
            self.assertEqual(hub.main(["ingest-intake", "--apply"]), 0)


class MailRelayTests(unittest.TestCase):
    def setUp(self):
        sys.modules.setdefault("google", mock.MagicMock())
        for m in ("google.auth", "google.auth.transport", "google.auth.transport.requests", "google.oauth2",
                  "google.oauth2.credentials", "googleapiclient", "googleapiclient.discovery"):
            sys.modules.setdefault(m, mock.MagicMock())
        import jarvis_grok_bucho_mail_apply as gm

        self.gm = gm

    def test_off_by_default(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertFalse(self.gm.intake_relay_enabled())
        with mock.patch.dict(os.environ, {"JARVIS_GROK_INTAKE_RELAY": "1", "COMM_INTAKE_URL": "https://x"}, clear=True):
            self.assertFalse(self.gm.intake_relay_enabled())  # 鍵が無ければオフ
        with mock.patch.dict(os.environ, {"JARVIS_GROK_INTAKE_RELAY": "1", "COMM_INTAKE_URL": "https://x", "COMM_INTAKE_KEY": "k"}, clear=True):
            self.assertTrue(self.gm.intake_relay_enabled())

    def test_item_shape(self):
        it = self.gm.intake_item_from_mail(
            {"id": "18c", "subject": "[Grok部長] 11/11 日報", "date": "Tue, 11 Nov 2026 08:00:00 +0900", "body": "本文"}
        )
        self.assertEqual(it["bot_item_id"], "mail:18c")
        self.assertEqual(it["kind"], "agent")
        self.assertEqual(it["occurred_at"], "2026-11-10T23:00:00+00:00")
        self.assertEqual(it["refs"]["via"], "mail")
        self.assertNotIn("bot", it)  # 送り手は鍵で決まる


if __name__ == "__main__":
    unittest.main()
