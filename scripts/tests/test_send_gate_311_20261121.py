# -*- coding: utf-8 -*-
"""311 送信前品質係 P0（2026-11-21）: 重複排除・restore が処理済み依頼を戻さない。

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


def run(body: str, partner=PARTNER, **kw):
    return gate.run_checks(
        draft_path=Path("/tmp/x.txt"), body=body, source="manual", partner=partner, cfg=CFG, **kw
    )


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
