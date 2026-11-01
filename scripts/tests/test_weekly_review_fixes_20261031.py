#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""314 週次レビュー 2026-10-31 の修正分（ネットワーク不要）。

- 311 送信ゲート: Drive 未同期の下書き 1 件で poll 全体を落とさない
- 部長メール取込: gmail.modify 不足の 403 は 1 回だけ書いて片付けを止める
- 部長ブリッジ: apply 失敗ログに stderr の最後の行を出す
- 機械チェック: workflow のコメント行を依存判定に数えない／Gemini 追加を拾う
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))

import jarvis_bucho_inbox_poll as bridge  # noqa: E402
import jarvis_grok_bucho_mail_apply as bucho  # noqa: E402
import jarvis_send_gate_311 as gate  # noqa: E402
import jarvis_weekly_review_314 as wr  # noqa: E402


class SendGateDraftNotReadyTests(unittest.TestCase):
    def test_read_draft_raises_not_ready(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "draft.md"
            p.write_text("x", encoding="utf-8")
            with mock.patch.object(gate, "read_text_cloud", return_value=None):
                with self.assertRaises(gate.DraftNotReady):
                    gate._read_draft(p)

    def test_inbox_continues_and_keeps_unreadable_md(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            inbox = root / "input"
            inbox.mkdir()
            for name in ("a", "b"):
                (root / f"{name}.md").write_text("本文", encoding="utf-8")
                (inbox / f"req_{name}.md").write_text(
                    f"draft_path: {root / (name + '.md')}\nsource: manual\n", encoding="utf-8"
                )
            calls: list[str] = []

            def fake(draft, source, **k):
                calls.append(draft.name)
                if draft.name == "a.md":
                    raise gate.DraftNotReady("not ready")
                return 0

            argv = ["gate", "--from-inbox", str(inbox), "--dry-run"]
            with mock.patch.object(gate, "_load_env"), mock.patch.object(
                gate, "_process_one", side_effect=fake
            ), mock.patch.object(sys, "argv", argv):
                code = gate.main()
            self.assertEqual(sorted(calls), ["a.md", "b.md"])
            self.assertEqual(code, 1)
            # 読めなかった a は次回のため inbox に残り、b は processed へ
            self.assertTrue((inbox / "req_a.md").exists())
            self.assertFalse((inbox / "req_b.md").exists())
            self.assertTrue((inbox / "processed" / "req_b.md").exists())


class BuchoScopeErrorTests(unittest.TestCase):
    def test_scope_error_detected(self):
        e = Exception(
            '<HttpError 403 ... returned "Request had insufficient authentication scopes.">'
        )
        self.assertTrue(bucho.is_scope_error(e))
        self.assertFalse(bucho.is_scope_error(Exception("HttpError 500 backendError")))

    def test_archive_stops_after_first_scope_error(self):
        msgs = [{"id": f"m{i}", "body": "", "subject": "[Grok部長] x"} for i in range(5)]
        calls = {"n": 0}

        def archive(*a, **k):
            calls["n"] += 1
            raise Exception("Request had insufficient authentication scopes.")

        with mock.patch.object(bucho, "gmail_service", return_value=object()), mock.patch.object(
            bucho, "load_state", return_value={"processed_ids": [m["id"] for m in msgs]}
        ), mock.patch.object(bucho, "fetch_bucho_messages", return_value=msgs), mock.patch.object(
            bucho, "_bucho_label_id", return_value="L"
        ), mock.patch.object(bucho, "archive_processed", side_effect=archive), mock.patch.object(
            bucho, "_keep_inbox", return_value=False
        ), mock.patch.object(bucho, "save_state"):
            with mock.patch("sys.stdout"):
                bucho.apply_from_gmail(dry_run=False, days=3, reprocess=False)
        self.assertEqual(calls["n"], 1)


class BridgeErrLineTests(unittest.TestCase):
    def test_last_line(self):
        tail = '  rs="replace")\n           ^^^^^\nOSError: [Errno 11] Resource deadlock avoided\n\n'
        self.assertEqual(bridge._err_line(tail), "OSError: [Errno 11] Resource deadlock avoided")
        self.assertEqual(bridge._err_line(None), "")


class WeeklyReviewDetectTests(unittest.TestCase):
    def test_comment_lines_not_counted_as_deps(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / ".github" / "workflows").mkdir(parents=True)
            (root / "scripts").mkdir()
            (root / "scripts" / "uses_yaml.py").write_text("import yaml\n", encoding="utf-8")
            (root / ".github" / "workflows" / "a.yml").write_text(
                "# Mac の scripts/uses_yaml.py が定刻に起動する\njobs: {}\n", encoding="utf-8"
            )
            (root / ".github" / "workflows" / "b.yml").write_text(
                "steps:\n  - run: python scripts/uses_yaml.py\n", encoding="utf-8"
            )
            with mock.patch.object(wr, "REPO", root):
                self.assertEqual(wr.collect_workflow_deps(), ["b.yml: pyyaml"])

    def test_gemini_calls_detected(self):
        for ln in (
            "const gem = await geminiReply(prompt, { maxAttempts: 1 });",
            "out = gemini.generate(prompt, api_key=key, model=model).strip()",
            "GEMINI_API_KEY: ${{ secrets.GEMINI_API_KEY }}",
        ):
            self.assertTrue(wr.AI_CALL_RE.search(ln), ln)
        self.assertFalse(wr.AI_CALL_RE.search("# Gemini の説明だけのコメント"))


if __name__ == "__main__":
    unittest.main()
