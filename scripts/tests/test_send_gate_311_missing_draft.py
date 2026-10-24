#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""311 inbox: 下書きが消えた依頼は error_ に退避し、後続の依頼を止めない."""
from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "scripts"
sys.path.insert(0, str(SCRIPTS))


def _load():
    path = SCRIPTS / "jarvis_send_gate_311.py"
    spec = importlib.util.spec_from_file_location("jarvis_send_gate_311", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod  # dataclass 解決に必要
    spec.loader.exec_module(mod)
    return mod


gate = _load()


class TestMissingDraft(unittest.TestCase):
    def test_missing_draft_moves_to_error_and_continues(self):
        with tempfile.TemporaryDirectory() as d:
            inbox = Path(d)
            ok_draft = inbox / "ok.txt"
            ok_draft.write_text("本文", encoding="utf-8")
            gone = inbox / "a_gone.md"
            gone.write_text(f"draft_path: {inbox / 'missing.txt'}\nsource: 211\n", encoding="utf-8")
            ok = inbox / "b_ok.md"
            ok.write_text(f"draft_path: {ok_draft}\nsource: 211\n", encoding="utf-8")

            calls: list[Path] = []

            def fake_process(draft, source, **kw):
                calls.append(draft)
                return 0

            argv = ["x", "--from-inbox", str(inbox), "--dry-run"]
            with mock.patch.object(gate, "_load_env"), \
                    mock.patch.object(gate, "_load_yaml", return_value={}), \
                    mock.patch.object(gate, "_process_one", side_effect=fake_process), \
                    mock.patch.object(sys, "argv", argv):
                code = gate.main()

            self.assertEqual(code, 2)
            self.assertEqual(calls, [ok_draft])
            self.assertTrue((inbox / "processed" / "error_a_gone.md").exists())
            self.assertFalse(gone.exists())


if __name__ == "__main__":
    unittest.main()
