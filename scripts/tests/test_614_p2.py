"""614 第3稿 P2 — 判断ログ・有効基準（22〜24）／障害識別・自動復旧・履歴（33〜35）／Markdown 自動生成（36）。

架空の値だけ。外部サービス・AI には触れない（#ops 通知・push はモック）。ログは一時フォルダ。
"""
import json
import os
import re
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest import mock
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import jarvis_614_decisions as dec  # noqa: E402
import jarvis_614_display as dsp  # noqa: E402
import jarvis_614_incidents as inc  # noqa: E402
import jarvis_614_knowledge as kn  # noqa: E402
import jarvis_614_ops as ops  # noqa: E402
import jarvis_614_runlog as rl  # noqa: E402
import jarvis_614_verified_state as vs  # noqa: E402

JST = ZoneInfo("Asia/Tokyo")
KEY = "card_benefit.allocation"
REPO = Path(__file__).resolve().parents[2]
FLOW_DIR = REPO / "docs" / "AIエージェントチーム" / "600_リソース・家計室" / "614_ポイント・還元ウォッチ係"


def at(y, m, d):
    return datetime(y, m, d, 12, 0, tzinfo=JST)


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)
        p = mock.patch.dict(os.environ, {
            "JARVIS_STATE_DIR": str(self.dir),
            "JARVIS_614_LOG_DIR": str(self.dir / "614_watch"),
            "JARVIS_614_EMERGENCY_DIR": str(self.dir / "emergency"),
        })
        p.start()
        self.addCleanup(p.stop)
        for k in ("JARVIS_614_GLOBAL_STOP", "JARVIS_614_OPS_ACTIVE", "JARVIS_614_RUN_ID"):
            os.environ.pop(k, None)
        n = mock.patch.object(ops, "notify_ops", return_value={"status": "sent"})
        self.notify = n.start()
        self.addCleanup(n.stop)

    def decide(self, **kw):
        base = dict(topic=KEY, item="寄せ先の判断基準", choice="adopted", scope="standing")
        base.update(kw)
        return dec.record_decision(**base)["decision_id"]


# ------------------------------------------------------------------ 判断ログ（工程22・23）

class DecisionLogTests(Base):
    def test_reason_is_kept_verbatim_and_never_fabricated(self):
        a = self.decide(reason_text="  年会費の前に判断したいから  ")
        b = self.decide(reason_text=None)
        c = self.decide(reason_text="   ")
        v = dec.fold(dec.load_events_strict())
        self.assertEqual(v[a]["reason_text"], "年会費の前に判断したいから")
        self.assertIsNone(v[b]["reason_text"])  # 理由が無ければ補作しない
        self.assertIsNone(v[c]["reason_text"])

    def test_record_fields_and_validation(self):
        did = self.decide(ai_proposal="Olive を推奨", target="card_benefit", expires_at="2027-03-31",
                          run_id="r1", incident_ids=["inc-x"])
        v = dec.fold(dec.load_events_strict())[did]
        for k in ("decision_id", "item", "ai_proposal", "choice", "reason_text", "target", "scope",
                  "expires_at", "run_id", "incident_ids", "revoked", "history"):
            self.assertIn(k, v)
        self.assertTrue(did.startswith("dec-"))
        with self.assertRaises(ValueError):
            self.decide(choice="maybe")
        with self.assertRaises(ValueError):
            self.decide(expires_at="来月")

    def test_held_declined_this_time_are_not_adopted_as_criteria(self):
        self.decide(choice="held")
        self.decide(choice="declined")
        self.decide(choice="adopted", scope="this_time")
        r = dec.criteria_for("card_benefit", at(2026, 12, 1))
        self.assertEqual(r["status"], "ok")
        self.assertEqual(r["applied"], [])
        self.assertEqual(r["waiting"], [])
        self.assertEqual(len(r["reference"]), 3)  # 参考表示には出るが適用しない

    def test_adopted_standing_within_deadline_is_applied_and_id_recorded_in_run(self):
        did = self.decide(expires_at="2027-03-31")
        rec = rl.RunRecord(run_id="run-1")
        res = rec.apply_criteria("card_benefit", at(2026, 12, 1))
        self.assertEqual([a["decision_id"] for a in res["applied"]], [did])
        d = rec.to_dict()
        self.assertEqual(d["applied_decisions"][0]["decision_id"], did)
        self.assertEqual(d["applied_decisions"][0]["result"], "applied")
        self.assertEqual(d["systems"]["card_benefit"]["stages"]["criteria"]["status"], "success")

    def test_no_deadline_stays_effective(self):
        self.decide(expires_at=None)
        self.assertEqual(len(dec.criteria_for("card_benefit", at(2035, 1, 1))["applied"]), 1)

    def test_deadline_day_is_inclusive_then_expired(self):
        self.decide(expires_at="2026-12-31")
        self.assertEqual(len(dec.criteria_for("card_benefit", at(2026, 12, 31))["applied"]), 1)
        r = dec.criteria_for("card_benefit", at(2027, 1, 1))
        self.assertEqual(r["applied"], [])
        self.assertEqual(len(r["waiting"]), 1)

    def test_expired_is_not_applied_shown_as_reference_and_recommendation_stops(self):
        did = self.decide(expires_at="2026-11-30", reason_text="理由A")
        r = dec.criteria_for("card_benefit", at(2026, 12, 15))
        self.assertEqual(r["applied"], [])
        self.assertEqual(r["waiting"][0]["decision_id"], did)
        self.assertEqual(r["reference"][0]["decision_id"], did)  # 参考表示
        rec = {"card": "olive", "line": "Olive（…）"}
        gated = dec.gate_recommendation(rec, r)
        self.assertIsNone(gated["card"])
        self.assertTrue(gated["withheld"])
        self.assertIn("再判断待ち", gated["line"])
        self.assertEqual(gated["reference"], [did])
        # 取得済みの事実・数値は呼び出し側が表示する（推奨だけが止まる）
        self.assertEqual(rec["card"], "olive")

    def test_no_automatic_fallback_to_the_old_criterion(self):
        old = self.decide(expires_at="2026-06-30")
        self.decide(choice="declined")  # 新しい見送り・保留は採用ではない
        self.decide(choice="held")
        r = dec.criteria_for("card_benefit", at(2026, 12, 1))
        self.assertEqual(r["applied"], [])
        self.assertEqual(r["waiting"][0]["decision_id"], old)  # 古い基準へ戻らず、再判断待ちのまま
        new = self.decide(expires_at="2027-12-31")
        r2 = dec.criteria_for("card_benefit", at(2026, 12, 1))
        self.assertEqual([a["decision_id"] for a in r2["applied"]], [new])
        self.assertEqual(r2["waiting"], [])

    def test_revise_extends_and_keeps_history_revoke_stops(self):
        did = self.decide(expires_at="2026-11-30")
        self.assertTrue(dec.criteria_for("card_benefit", at(2026, 12, 15))["waiting"])
        dec.revise_decision(did, {"expires_at": "2027-06-30", "reason_text": "続けたい"})
        v = dec.fold(dec.load_events_strict())[did]
        self.assertEqual(len(v["history"]), 2)  # 元の判断も残る
        self.assertEqual(len(dec.criteria_for("card_benefit", at(2026, 12, 15))["applied"]), 1)
        dec.revoke_decision(did, None)
        r = dec.criteria_for("card_benefit", at(2026, 12, 15))
        self.assertEqual((r["applied"], r["waiting"]), ([], []))  # 取消は適用しない
        with self.assertRaises(ValueError):
            dec.revise_decision(did, {"choice": "adopted"})
        self.assertEqual(len(dec.fold(dec.load_events_strict())[did]["history"]), 3)

    def test_unreadable_log_is_read_error_not_no_criteria_and_only_that_system(self):
        self.decide()
        with open(dec.decisions_path(), "a", encoding="utf-8") as f:
            f.write("{壊れた行\n")
        r = dec.criteria_for("card_benefit")
        self.assertEqual(r["status"], "read_error")
        gated = dec.gate_recommendation({"card": "olive", "line": "x"}, r)
        self.assertTrue(gated["withheld"])
        self.assertEqual(gated["criteria_hold"], "read_error")
        # 基準を使わない系統（teiki・etc・vpoint）は影響を受けない
        for s in ("teiki", "etc", "vpoint"):
            self.assertEqual(dec.criteria_for(s)["status"], "none")
        # 壊れたログへは追記しない（取消が効かなくなるのを防ぐ）
        with self.assertRaises(dec.DecisionLogError):
            self.decide()
        rec = rl.RunRecord(run_id="r")
        rec.apply_criteria("card_benefit")
        st = rec.to_dict()["systems"]["card_benefit"]["stages"]["criteria"]
        self.assertEqual((st["status"], st["error_code"]), ("failed", "criteria_read_error"))

    def test_no_decision_registered_keeps_existing_behaviour(self):
        r = dec.criteria_for("card_benefit")
        self.assertEqual((r["status"], r["applied"], r["waiting"]), ("ok", [], []))
        rec = {"card": "olive", "line": "x"}
        self.assertEqual(dec.gate_recommendation(rec, r), rec)
        self.assertEqual(dec.gate_recommendation(rec, None), rec)

    def test_cli_record_list_revoke(self):
        self.assertEqual(dec.main(["record", "--topic", KEY, "--item", "寄せ先", "--choice", "adopted",
                                   "--scope", "standing", "--reason", "本人の言葉"]), 0)
        did = next(iter(dec.fold(dec.load_events_strict())))
        self.assertEqual(dec.main(["revise", did, "--expires", "2027-01-31"]), 0)
        self.assertEqual(dec.main(["revoke", did]), 0)
        self.assertEqual(dec.main(["revoke", did]), 1)  # 二重取消は拒否
        self.assertEqual(dec.main(["list"]), 0)


# ------------------------------------------------------------------ 障害識別・自動復旧（工程33〜35）

class IncidentTests(Base):
    def occ(self, run, code="save_verify_mismatch", stage="save_verify", system="card_benefit", cat="failed"):
        return inc.begin_occurrence(system=system, stage=stage, category=cat, error_code=code, run_id=run,
                                    fact="読み戻しが一致しない")

    def test_identity_is_system_stage_category_code_and_missing_code_is_no_code(self):
        a, b = self.occ("r1"), self.occ("r2")
        self.assertEqual(a.key, b.key)
        self.assertNotEqual(a.key, self.occ("r3", code="other").key)
        self.assertNotEqual(a.key, self.occ("r4", stage="display").key)
        self.assertNotEqual(a.key, self.occ("r5", system="etc").key)
        self.assertTrue(self.occ("r6", code=None).key.endswith("|no_code"))

    def test_same_run_same_key_counts_once(self):
        self.occ("r1")
        o = self.occ("r1")
        self.assertEqual(o.count, 1)

    def test_third_consecutive_occurrence_stops_the_auto_remedy_but_not_other_systems(self):
        self.assertTrue(self.occ("r1").may_auto("save_retry")[0])
        self.assertTrue(self.occ("r2").may_auto("save_retry")[0])
        third = self.occ("r3")
        ok, why = third.may_auto("save_retry")
        self.assertFalse(ok)  # 3回目には実行しない
        self.assertIn("停止", why)
        self.assertEqual(self.notify.call_count, 1)  # 停止を #ops へ（再帰しない通知の土台を使う）
        st = inc.load_state()
        self.assertIn("save_retry", st["keys"][third.key]["suspended"])
        # 他の系統・別の障害は止まらない
        self.assertTrue(self.occ("r3", system="etc").may_auto("save_retry")[0])
        self.assertTrue(self.occ("r3", code="other").may_auto("save_retry")[0])
        # 4回目以降も止まったまま
        self.assertFalse(self.occ("r4").may_auto("save_retry")[0])

    def test_auto_recovery_success_alone_does_not_reset_the_count(self):
        for r in ("r1", "r2"):
            o = self.occ(r)
            self.assertTrue(o.may_auto("save_retry")[0])
            o.record_remedy("save_retry", "success", "やり直しで一致")
        self.assertEqual(inc.load_state()["keys"][o.key]["count"], 2)
        # その run が『保存OK』で終わっても（自動復旧の成功）、同じ run の障害があるのでリセットしない
        run = {"run_id": "r2", "dry_run": False, "systems": {"card_benefit": {"stages": {
            "save_verify": {"status": "success", "detail": "", "error_code": None}}}}}
        inc.observe_run(run)
        self.assertEqual(inc.load_state()["keys"][o.key]["count"], 2)
        self.assertFalse(self.occ("r3").may_auto("save_retry")[0])

    def test_next_normal_success_resets_but_skip_stop_dry_run_and_other_system_do_not(self):
        o = self.occ("r1")
        self.occ("r2")
        key = o.key

        def run(rid, status, system="card_benefit", dry=False, stage="save_verify"):
            return {"run_id": rid, "dry_run": dry, "systems": {system: {"stages": {
                stage: {"status": status, "detail": "", "error_code": None}}}}}

        for r in (run("n1", "skipped"), run("n2", "not_applicable"), run("n3", "success", dry=True),
                  run("n4", "success", system="etc"), run("n5", "success", stage="fetch"),
                  run("n6", "unverified"), run("n7", "partial"), run("n8", "waiting")):
            inc.observe_run(r)
        self.assertEqual(inc.load_state()["keys"][key]["count"], 2)
        inc.observe_run(run("n9", "success"))  # 該当工程の通常実行が成功
        self.assertEqual(inc.load_state()["keys"][key]["count"], 0)
        self.assertTrue(self.occ("r10").may_auto("save_retry")[0])  # 1回目から数え直し

    def test_suspension_survives_reset_and_resume_needs_records_and_explicit_approval(self):
        o = None
        for r in ("r1", "r2", "r3"):
            o = self.occ(r)
            o.may_auto("save_retry")
        key = o.key
        inc.observe_run({"run_id": "ok", "dry_run": False, "systems": {"card_benefit": {"stages": {
            "save_verify": {"status": "success", "detail": "", "error_code": None}}}}})
        self.assertEqual(inc.load_state()["keys"][key]["count"], 0)
        # 通常実行が成功して回数が戻っても、停止した自動対策は明示承認なしに再開しない
        self.assertFalse(self.occ("r5").may_auto("save_retry")[0])
        # 原因・対策・検証結果の記録が無いと承認できない
        with self.assertRaises(ValueError) as cm:
            inc.approve_resume(key, "save_retry", "再開してよい")
        self.assertIn("原因", str(cm.exception))
        self.assertIn("検証", str(cm.exception))
        iid = inc.load_state()["keys"][key]["incident_ids"][0]
        inc.annotate(iid, cause="保存先の空き容量不足", cause_kind="fact", decision_ids=["dec-x"])
        with self.assertRaises(ValueError):
            inc.approve_resume(key, "save_retry", "再開してよい")  # 検証結果がまだ
        self.assertEqual(inc.main(["remedy", iid, "--remedy-id", "manual_cleanup", "--outcome", "success",
                                   "--verification", "空きを確保し読み戻し一致を確認"]), 0)
        with self.assertRaises(ValueError):
            inc.approve_resume(key, "save_retry", "   ")  # 承認の文言なし
        self.assertFalse(self.occ("r6").may_auto("save_retry")[0])  # まだ止まっている
        inc.approve_resume(key, "save_retry", "松野さん了承: 再開してよい")
        self.assertTrue(self.occ("r7").may_auto("save_retry")[0])  # 承認後は1回目から

    def test_blocked_and_unapproved_remedies_are_recorded_and_presented_to_the_human(self):
        o = self.occ("r1", code="draw_error", stage="fetch", system="teiki")
        ok, why = o.may_auto("draw_retry")
        self.assertFalse(ok)
        self.assertIn("二重抽選", why)
        ok2, _ = o.may_auto("unknown_remedy")
        self.assertFalse(ok2)
        rems = inc.load_state()["incidents"][o.incident_id]["remedies"]
        self.assertEqual([r["outcome"] for r in rems], ["not_approved", "not_approved"])
        self.assertTrue(all(r["auto"] is False for r in rems))
        brief = inc.human_brief("teiki", "fetch", "draw_error")
        self.assertIn(o.incident_id, brief)
        self.assertIn("save_retry", brief)  # 承認済みの対策候補

    def test_failed_remedy_is_kept(self):
        o = self.occ("r1")
        self.assertTrue(o.may_auto("save_retry")[0])
        o.record_remedy("save_retry", "failed", "やり直しも不一致")
        r = inc.load_state()["incidents"][o.incident_id]["remedies"]
        self.assertEqual((r[0]["outcome"], r[0]["verification"]), ("failed", "やり直しも不一致"))

    def test_history_search_is_deterministic_and_separates_fact_cause_decision(self):
        a = self.occ("r1")
        b = self.occ("r2", code="other")
        self.occ("r3", stage="display", code="display_failed")
        inc.annotate(a.incident_id, cause="容量不足", cause_kind="fact", decision_ids=["dec-1"])
        inc.annotate(a.incident_id, cause="一時的なI/O", cause_kind="inferred")
        h1 = inc.search_history("card_benefit", "save_verify", "save_verify_mismatch")
        h2 = inc.search_history("card_benefit", "save_verify", "save_verify_mismatch")
        self.assertEqual(h1, h2)
        self.assertEqual([i["incident_id"] for i in h1["exact"]], [a.incident_id])
        self.assertEqual([i["incident_id"] for i in h1["related"]], [b.incident_id])  # 同じ工程の別障害
        ex = h1["exact"][0]
        self.assertEqual(ex["fact"], "読み戻しが一致しない")
        self.assertEqual(ex["cause_confirmed"], ["容量不足"])
        self.assertEqual(ex["cause_inferred"], ["一時的なI/O"])
        self.assertEqual(ex["decision_ids"], ["dec-1"])

    def test_unreadable_incident_log_never_allows_an_auto_remedy(self):
        self.occ("r1")
        with open(inc.incidents_path(), "a", encoding="utf-8") as f:
            f.write("壊れた\n")
        o = self.occ("r2")
        self.assertFalse(o.may_auto("save_retry")[0])
        self.assertIn("emergency", " ".join(str(p) for p in (self.dir / "emergency").rglob("*")))

    def test_observe_run_records_failed_and_unverified_only_and_skips_dry_run(self):
        run = {"run_id": "r1", "dry_run": False, "systems": {"etc": {"stages": {
            "fetch": {"status": "failed", "detail": "ログイン失敗", "error_code": "login_failed"},
            "display": {"status": "unverified", "detail": "読み戻せず", "error_code": None},
            "stamp": {"status": "waiting", "detail": "", "error_code": None},
            "slack": {"status": "partial", "detail": "", "error_code": None}}}}}
        out = inc.observe_run(dict(run, dry_run=True))
        self.assertEqual(out["occurred"], 0)
        self.assertEqual(inc.observe_run(run)["occurred"], 2)
        self.assertEqual(inc.observe_run(run)["occurred"], 0)  # 同じ run は二重に数えない
        keys = set(inc.load_state()["keys"])
        self.assertEqual(keys, {"etc|fetch|failed|login_failed", "etc|display|unverified|no_code"})

    def test_runrecord_finish_feeds_incidents_and_three_logs_are_traceable(self):
        did = self.decide(expires_at="2027-03-31", run_id="r-dec", incident_ids=[])
        rec = rl.RunRecord(run_id="r-trace", script="x.py")
        rec.apply_criteria("card_benefit", at(2026, 12, 1))
        rec.stage("card_benefit", "fetch", "failed", "取得失敗", "olive_gmail_failed")
        rec.finish()
        runs = rl.read_runs()
        self.assertEqual(runs[0]["run_id"], "r-trace")
        self.assertEqual(runs[0]["applied_decisions"][0]["decision_id"], did)
        incs = inc.load_state()["incidents"]
        (i,) = incs.values()
        self.assertEqual(i["run_id"], "r-trace")  # runs ↔ incidents
        inc.annotate(i["incident_id"], cause="Gmail 認証切れ", cause_kind="inferred", decision_ids=[did])
        self.assertEqual(inc.load_state()["incidents"][i["incident_id"]]["decision_ids"], [did])  # incidents ↔ decisions

    def test_finish_never_raises_even_if_incident_log_is_broken(self):
        inc.incidents_path().parent.mkdir(parents=True, exist_ok=True)
        inc.incidents_path().write_text("壊れた\n", encoding="utf-8")
        rec = rl.RunRecord(run_id="r1")
        rec.stage("etc", "fetch", "failed", "x", "c")
        rec.finish()  # 例外を投げない
        self.assertEqual(len(rl.read_runs()), 1)


class RemedyWiringTests(Base):
    def _always_mismatch(self):
        return lambda read_back, expected: ["不一致: a"]

    def test_save_retry_runs_twice_then_stops_on_third_consecutive_failure(self):
        target = self.dir / "s.json"
        attempts = []
        for n in (1, 2, 3):
            os.environ["JARVIS_614_RUN_ID"] = f"run-{n}"
            res = vs.save_json_verified(target, {"a": 1}, verify=self._always_mismatch(),
                                        pending_path=self.dir / "s.pending.json", retries=1,
                                        remedy_system="card_benefit")
            attempts.append(res["attempts"])
            self.assertFalse(res["ok"])
            self.assertTrue((self.dir / "s.pending.json").is_file())  # 取得済みデータは残す
        self.assertEqual(attempts, [2, 2, 1])  # 3回目はやり直さない
        self.assertIn("停止中", " ".join(res["errors"]))
        st = inc.load_state()
        self.assertEqual(st["keys"]["card_benefit|save_verify|failed|save_verify_mismatch"]["count"], 3)
        outs = [r["outcome"] for i in st["incidents"].values() for r in i["remedies"]]
        self.assertIn("failed", outs)  # 失敗した対策も残る
        self.assertIn("blocked", outs)

    def test_without_remedy_system_behaviour_is_unchanged(self):
        res = vs.save_json_verified(self.dir / "s.json", {"a": 1}, verify=self._always_mismatch(),
                                    pending_path=self.dir / "p.json", retries=1)
        self.assertEqual(res["attempts"], 2)
        self.assertFalse(inc.incidents_path().exists())

    def test_save_retry_success_records_remedy_but_not_reset(self):
        calls = {"n": 0}

        def flaky(read_back, expected):
            calls["n"] += 1
            return ["不一致"] if calls["n"] == 1 else []

        os.environ["JARVIS_614_RUN_ID"] = "run-a"
        res = vs.save_json_verified(self.dir / "s.json", {"a": 1}, verify=flaky, retries=1, remedy_system="etc")
        self.assertTrue(res["ok"])
        st = inc.load_state()
        (i,) = st["incidents"].values()
        self.assertEqual([(r["remedy_id"], r["outcome"]) for r in i["remedies"]], [("save_retry", "success")])
        self.assertEqual(st["keys"][i["key"]]["count"], 1)  # 自動復旧の成功だけでは戻さない

    def test_repush_stops_on_third_consecutive_display_mismatch(self):
        pushes = []

        def pusher():
            pushes.append(1)
            return 0

        def bad_fetch(ids):
            return {i: None for i in ids}

        with mock.patch.object(dsp, "expected_for", return_value={"x": 1}), \
                mock.patch.object(dsp, "actual_from_row", return_value={"x": 2}), \
                mock.patch.object(dsp, "diff_fields", return_value=["x"]):
            counts = []
            for n in (1, 2, 3):
                os.environ["JARVIS_614_RUN_ID"] = f"d-{n}"
                pushes.clear()
                res = dsp.sync_and_verify(["vpoint"], pusher=pusher, fetcher=bad_fetch, remedy_system="vpoint")
                counts.append(len(pushes))
                self.assertEqual(res["display"], "failed")
            self.assertEqual(counts, [2, 2, 1])  # 3回目は再 push しない
            self.assertIn("停止中", res["error"])
            pushes.clear()
            dsp.sync_and_verify(["vpoint"], pusher=pusher, fetcher=bad_fetch)  # remedy_system なし＝従来どおり
            self.assertEqual(len(pushes), 2)


# ------------------------------------------------------------------ Markdown 自動生成（工程36）

class KnowledgeTests(Base):
    def seed(self):
        did = self.decide(reason_text="理由あり", expires_at="2027-03-31", ai_proposal="Olive")
        self.decide(choice="held", reason_text=None, item="保留の件")
        o = inc.begin_occurrence(system="etc", stage="fetch", category="failed", error_code="login_failed",
                                 run_id="r1", fact="ログイン失敗")
        inc.annotate(o.incident_id, cause="画面変更", cause_kind="inferred", decision_ids=[did])
        o.record_remedy("save_retry", "failed", "効果なし")
        return did, o

    def test_generated_from_source_is_deterministic_and_complete(self):
        did, o = self.seed()
        a = kn.generate()
        self.assertEqual(a, kn.generate())
        d = a["decisions.md"]
        self.assertIn(did, d)
        self.assertIn("理由あり", d)
        self.assertIn("理由なし（補作しない）", d)
        self.assertIn("自動生成", d)
        p = a["incident-playbook.md"]
        self.assertIn(o.incident_id, p)
        self.assertIn("画面変更", p)
        self.assertIn("login_failed", p)
        self.assertIn("draw_retry", p)  # 承認状況
        self.assertIn(did, p)  # 関連 decision_id

    def test_write_private_perms_regenerate_and_drift_detection(self):
        self.seed()
        paths = kn.write()
        self.assertEqual({p.name for p in paths}, {"decisions.md", "incident-playbook.md"})
        self.assertEqual(oct(paths[0].stat().st_mode & 0o777), "0o600")
        self.assertEqual(oct(paths[0].parent.stat().st_mode & 0o777), "0o700")
        self.assertEqual(kn.drift(), [])
        paths[0].write_text(paths[0].read_text(encoding="utf-8") + "手で足した行\n", encoding="utf-8")
        self.assertTrue(kn.drift())  # 手編集を検出
        kn.write()
        self.assertEqual(kn.drift(), [])  # 正本から再生成できる
        self.assertEqual(kn.main(["--check"]), 0)

    def test_cli_record_regenerates_markdown_automatically(self):
        self.assertEqual(dec.main(["record", "--topic", KEY, "--item", "寄せ先", "--choice", "adopted",
                                   "--scope", "standing"]), 0)
        self.assertEqual(kn.drift(), [])
        self.assertTrue((kn.knowledge_dir() / "decisions.md").is_file())


class NoAiNoNetworkTests(unittest.TestCase):
    def test_new_modules_never_call_ai_or_network_directly(self):
        bad = re.compile(r"^\s*(import|from)\s+(anthropic|openai|requests|urllib|http\.client|socket|google\.generativeai)\b", re.M)
        for name in ("decisions", "incidents", "knowledge"):
            src = (Path(__file__).resolve().parents[1] / f"jarvis_614_{name}.py").read_text(encoding="utf-8")
            self.assertIsNone(bad.search(src), name)
            self.assertNotIn("subprocess", src, name)  # 通知は ops を経由（このモジュールからは外へ出ない）


# ------------------------------------------------------------------ フロー3資料の整合

class FlowConsistencyTests(unittest.TestCase):
    def setUp(self):
        self.flow = json.loads((FLOW_DIR / "flow.json").read_text(encoding="utf-8"))
        self.html = (FLOW_DIR / "flow.html").read_text(encoding="utf-8")
        self.md = (FLOW_DIR / "flow.md").read_text(encoding="utf-8")

    def test_html_embedded_json_equals_flow_json(self):
        m = re.search(r'<script id="flowdata" type="application/json">(.*?)</script>', self.html, re.S)
        self.assertIsNotNone(m)
        self.assertEqual(json.loads(m.group(1)), self.flow)

    def test_every_node_and_edge_appears_in_md_mermaid_and_table(self):
        mer = re.search(r"```mermaid\n(.*?)```", self.md, re.S).group(1)
        for n in self.flow["nodes"]:
            self.assertIn(f'{n["id"]}["', mer, n["id"])
            self.assertRegex(self.md, rf"\|\s*{n['number']}\s*\|", n["id"])
        for e in self.flow["edges"]:
            self.assertRegex(mer, rf"{e['from']}\s+[-=.]+[>]?\|?.*?{e['to']}|{e['from']}\s+[-=.]+>?\s*{e['to']}", f"{e['from']}->{e['to']}")

    def test_p2_nodes_exist_with_mapping_and_status(self):
        by = {n["id"]: n for n in self.flow["nodes"]}
        for i in ("n35", "n36", "n37", "n38"):
            self.assertIn(i, by)
            self.assertEqual(by[i]["actor"], "プログラム")
            self.assertIn("task_step", by[i])
        self.assertEqual([by[i]["task_step"] for i in ("n35", "n36", "n37", "n38")], [33, 34, 35, 36])
        self.assertEqual(self.flow["runtime_ai_nodes"], 0)
        # 既存の n33・n34（Tサイト定期取得・Vpass 残高）は動かさない
        self.assertIn("Tサイト", by["n33"]["title"])
        self.assertIn("Vpass", by["n34"]["title"])


if __name__ == "__main__":
    unittest.main()
