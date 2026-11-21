# -*- coding: utf-8 -*-
"""311 送信前品質係 P0（2026-11-21）: 重複排除・3状態判定・restore が処理済み依頼を戻さない。

取引先名・実アドレスは使わない（ダミー名・example ドメインのみ）。
"""
from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))


def _load(name: str, fname: str):
    spec = importlib.util.spec_from_file_location(name, REPO / "scripts" / fname)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    assert spec.loader
    spec.loader.exec_module(mod)
    return mod


gate = _load("jarvis_send_gate_311", "jarvis_send_gate_311.py")
pds = _load("private_data_sync", "private_data_sync.py")

CFG = {
    "email_substrings": ["noreply@"],
    "text_keywords": ["ポータル運営"],
    "allowed_from_emails": ["me@example.com"],
    "greet_email_hints": {"山田": "yamada@example.net"},
}
PARTNER = {"folder": "P900_ダミー社", "name": "ダミー社", "emails": ["yamada@example.net"]}


def run(body: str, partner=PARTNER, source="manual", **kw):
    return gate.run_checks(
        draft_path=Path("/tmp/x.txt"), body=body, source=source, partner=partner, cfg=CFG, **kw
    )


class ThreeStateTest(unittest.TestCase):
    def test_all_verified_is_ok(self) -> None:
        r = run("From: me@example.com\nTo: yamada@example.net\n\n山田様\n本文")
        self.assertEqual(r.overall, "OK")
        self.assertEqual(gate.exit_code_of(r.overall), 0)

    def test_no_from_known_route_sender_ok(self) -> None:
        for src in ("manual", "211", "s9", "hawk", "s2", "kurashift_inquiry"):
            r = run("To: yamada@example.net\n\n山田様\n本文", source=src)
            sender = [c for c in r.checks if c.code == "sender"][0]
            self.assertEqual(sender.status, "ok", src)
            self.assertIn("経路で本人名義を確認", sender.detail)
            self.assertEqual(r.overall, "OK", src)

    def test_no_from_unknown_route_is_review_not_ok(self) -> None:
        r = run("To: yamada@example.net\n\n山田様\n本文", source="unknown_x")
        self.assertEqual(r.overall, "REVIEW")
        self.assertNotEqual(gate.exit_code_of(r.overall), 0)
        self.assertEqual({c.code: c.status for c in r.checks}["sender"], "unverified")

    def test_explicit_foreign_from_is_ng_even_on_known_route(self) -> None:
        r = run("From: someone@example.org\nTo: yamada@example.net\n\n本文", source="211")
        self.assertEqual(r.overall, "NG")

    def test_sender_spoof_is_ng(self) -> None:
        r = run("From: someone@example.org\nTo: yamada@example.net\n\n山田様\n本文")
        self.assertEqual(r.overall, "NG")
        self.assertEqual(gate.exit_code_of(r.overall), 10)

    def test_empty_to_is_review(self) -> None:
        r = run("From: me@example.com\nTo:\n件名: テスト\n\n本文")
        self.assertEqual(r.overall, "REVIEW")
        dest = [c for c in r.checks if c.code == "dest"][0]
        self.assertEqual(dest.status, "unverified")
        self.assertIn("To空欄", dest.detail)

    def test_partner_unknown_is_review(self) -> None:
        r = run("From: me@example.com\n\n本文", partner=None)
        self.assertEqual(r.overall, "REVIEW")

    def test_kurashift_dest_without_check_is_ok(self) -> None:
        r = run("To: broker@example.net\n\n本文", partner=None, source="kurashift_inquiry")
        dest = [c for c in r.checks if c.code == "dest"][0]
        self.assertEqual(dest.status, "ok")
        self.assertIn("物件ゲートで本人承認済み", dest.detail)
        self.assertEqual(r.overall, "OK")
        self.assertEqual(gate.exit_code_of(r.overall), 0)

    def test_kurashift_banned_dest_is_still_ng(self) -> None:
        r = run("To: noreply@example.net\n\n本文", partner=None, source="kurashift_inquiry")
        self.assertEqual(r.overall, "NG")

    def test_kurashift_foreign_from_is_still_ng(self) -> None:
        r = run("From: someone@example.org\nTo: broker@example.net\n\n本文", partner=None,
                source="kurashift_inquiry")
        self.assertEqual(r.overall, "NG")

    def test_other_source_dest_skip_stays_review(self) -> None:
        for src in ("manual", "211", "s9", "hawk", "s2"):
            r = run("To: broker@example.net\n\n本文", partner=None, source=src)
            self.assertEqual(r.overall, "REVIEW", src)
            r2 = run("本文", partner=PARTNER, source=src)  # 紐づけのみ
            self.assertEqual(r2.overall, "REVIEW", src)

    def test_legacy_kurashift_dest_ok(self) -> None:
        d = "パートナー未特定のため宛先照合はスキップ（パスに三桁フォルダ推奨）"
        self.assertEqual(gate.legacy_status(True, d, "dest", "kurashift_inquiry"), "ok")
        self.assertEqual(gate.legacy_status(True, d, "dest", "manual"), "unverified")

    def test_banned_is_ng_over_review(self) -> None:
        r = run("To: noreply@example.net\n\n本文")
        self.assertEqual(r.overall, "NG")

    def test_greeting_word_is_not_a_name(self) -> None:
        self.assertEqual(gate._greet_names("お疲れ様です。\n皆様\nご担当様\n山田様"), ["山田"])

    def test_parent_folder_is_not_partner(self) -> None:
        with mock.patch.object(gate, "_load_yaml", return_value={"partners": []}):
            p = gate._partner_from_path(Path("/x/215_神・大家さん倶楽部/000_共通/4.送信下書き.txt"))
        self.assertIsNone(p)

    def test_legacy_json_reclassified(self) -> None:
        d = "From明示なし（送信経路側で本人名義想定）"
        self.assertEqual(gate.legacy_status(True, d, "sender", "manual"), "ok")
        self.assertEqual(gate.legacy_status(True, d, "sender", "zzz"), "unverified")
        self.assertEqual(gate.legacy_status(True, "パートナー紐づけのみ確認（x）。To明示なし"), "unverified")
        self.assertEqual(gate.legacy_status(True, "禁止宛先なし"), "ok")
        self.assertEqual(gate.legacy_status(False, "x"), "ng")

    def test_review_slack_goes_to_consult_with_label(self) -> None:
        r = run("To: yamada@example.net\n\n山田様\n本文", source="unknown_x")
        ch, text = gate._format_slack(r)
        self.assertEqual(ch, "consult")
        self.assertIn("要確認", text.splitlines()[1])
        for key in ("要約", "内訳", "見方", "次"):
            self.assertIn(f"- {key}", text)


class DedupeTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.inbox = root / "input"
        self.inbox.mkdir()
        self.draft = root / "draft.txt"
        self.draft.write_text("To: yamada@example.net\n\n山田様\n本文", encoding="utf-8")
        self.state = root / "seen.json"
        self.cfg = root / "banned.yaml"
        self.cfg.write_text("email_substrings: []\n", encoding="utf-8")

    def _put(self, name: str = "20261119_073300_manual_dummy.md") -> Path:
        p = self.inbox / name
        p.write_text(f"---\ndraft_path: {self.draft}\nsource: manual\n---\n", encoding="utf-8")
        return p

    def _run(self, *extra: str) -> tuple[int, list[str]]:
        posts: list[str] = []
        argv = ["x", "--from-inbox", str(self.inbox), "--post", "--state-path", str(self.state),
                "--config", str(self.cfg), *extra]
        with mock.patch.object(sys, "argv", argv), \
                mock.patch.object(gate, "_post_slack", side_effect=lambda ch, t: posts.append(ch) or 0), \
                mock.patch.object(gate, "_write_output", return_value=Path("/dev/null")), \
                mock.patch.object(gate, "_partner_from_path", return_value=PARTNER), \
                mock.patch.object(gate, "_load_env"), mock.patch("builtins.print"):
            code = gate.main()
        return code, posts

    def test_second_request_is_skipped_once_notified(self) -> None:
        self._put()
        _, posts = self._run()
        self.assertEqual(len(posts), 1)
        # restore が input へ戻した状況（同名）
        self._put()
        _, posts = self._run()
        self.assertEqual(posts, [])
        self.assertFalse(list(self.inbox.glob("2*.md")))  # 重複でも processed へ移る
        self.assertEqual(len(list((self.inbox / "processed").glob("2*.md"))), 2)

    def test_same_content_other_request_id_is_skipped(self) -> None:
        self._put()
        self._run()
        self._put("20261120_000000_manual_dummy.md")
        _, posts = self._run()
        self.assertEqual(posts, [])

    def test_changed_draft_is_rejudged(self) -> None:
        self._put()
        self._run()
        self.draft.write_text("To: yamada@example.net\n\n山田様\n本文を直した", encoding="utf-8")
        self._put()
        _, posts = self._run()
        self.assertEqual(len(posts), 1)

    def test_force_recheck_rejudges_and_leaves_history(self) -> None:
        self._put()
        self._run()
        self._put()
        _, posts = self._run("--force-recheck")
        self.assertEqual(len(posts), 1)
        hist = json.loads(self.state.read_text(encoding="utf-8"))["history"]
        self.assertEqual(hist[-1]["event"], "force_recheck")

    def test_failed_post_is_not_recorded(self) -> None:
        self._put()
        argv = ["x", "--from-inbox", str(self.inbox), "--post", "--state-path", str(self.state),
                "--config", str(self.cfg)]
        with mock.patch.object(sys, "argv", argv), \
                mock.patch.object(gate, "_post_slack", return_value=1), \
                mock.patch.object(gate, "_write_output", return_value=Path("/dev/null")), \
                mock.patch.object(gate, "_partner_from_path", return_value=PARTNER), \
                mock.patch.object(gate, "_load_env"), mock.patch("builtins.print"):
            gate.main()
        self.assertFalse(self.state.exists())


class RestoreTest(unittest.TestCase):
    REL = pds.INBOX_311 + "20261119_073300_manual_dummy.md"

    def test_processed_request_is_not_restored(self) -> None:
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            repo, priv = Path(a), Path(b)
            (priv / self.REL).parent.mkdir(parents=True)
            (priv / self.REL).write_text("x", encoding="utf-8")
            (repo / pds.INBOX_311 / "processed").mkdir(parents=True)
            (repo / pds.INBOX_311 / "processed" / "20261119_073300_manual_dummy.md").write_text("x")
            self.assertTrue(pds.already_processed(self.REL, repo))

    def test_suffixed_and_error_variants(self) -> None:
        with tempfile.TemporaryDirectory() as a:
            repo = Path(a)
            proc = repo / pds.INBOX_311 / "processed"
            proc.mkdir(parents=True)
            (proc / "20261119_073300_manual_dummy_073512.md").write_text("x")
            self.assertTrue(pds.already_processed(self.REL, repo))

    def test_unprocessed_request_and_other_files_still_restored(self) -> None:
        with tempfile.TemporaryDirectory() as a:
            repo = Path(a)
            (repo / pds.INBOX_311 / "processed").mkdir(parents=True)
            self.assertFalse(pds.already_processed(self.REL, repo))
            # 他の社員の非公開ファイルは対象外
            other = "215_kamiooya/C2_ルーティン作業/2026_x.md"
            self.assertFalse(pds.already_processed(other, repo))

    def test_cmd_restore_skips_processed(self) -> None:
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            repo, priv = Path(a), Path(b)
            for rel in (self.REL, pds.INBOX_311 + "20261120_000000_manual_new.md"):
                (priv / rel).parent.mkdir(parents=True, exist_ok=True)
                (priv / rel).write_text("x", encoding="utf-8")
            (repo / pds.INBOX_311 / "processed").mkdir(parents=True)
            (repo / pds.INBOX_311 / "processed" / "20261119_073300_manual_dummy.md").write_text("x")
            orig = pds.already_processed
            with mock.patch.object(pds, "REPO", repo), \
                    mock.patch.object(pds, "already_processed", lambda r: orig(r, repo)), \
                    mock.patch("builtins.print"):
                pds.cmd_restore(priv, False)
            self.assertFalse((repo / self.REL).exists())
            self.assertTrue((repo / pds.INBOX_311 / "20261120_000000_manual_new.md").exists())


if __name__ == "__main__":
    unittest.main()
