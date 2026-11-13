"""jarvis_flat_ai: 定額AIの順番・上限時の切替・Genspark 残高の下限（2026-11-13）。"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import jarvis_flat_ai as flat  # noqa: E402


class FlatAITest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(self.id().replace(".", "_"))
        p = mock.patch.object(flat, "STATE_PATH", Path("/tmp") / f"flat_ai_test_{self.tmp}.json")
        p.start()
        self.addCleanup(p.stop)
        flat.STATE_PATH.unlink(missing_ok=True)
        flat._gencode_used = 0

    def fake(self, behaviour):
        calls = []

        def make(name):
            def f(prompt, *, timeout, images=()):
                calls.append(name)
                b = behaviour.get(name, "ok")
                if b == "limit":
                    raise flat.LimitReached("usage limit reached")
                if b == "fail":
                    raise RuntimeError("boom")
                return f"{name}:{prompt}"
            return f
        return {k: make(k) for k in flat.PROVIDERS}, calls

    def test_orders(self):
        self.assertEqual(flat.provider_order(False), ["gencode", "codex", "cursor", "claude"])
        self.assertEqual(flat.provider_order(True), ["codex", "cursor", "claude"])

    def test_interactive_skips_gencode_and_falls_through(self):
        provs, calls = self.fake({"codex": "limit", "cursor": "fail"})
        with mock.patch.dict(flat.PROVIDERS, provs):
            res = flat.generate("hi", interactive=True)
        self.assertEqual(res.provider, "claude")
        self.assertEqual(calls, ["codex", "cursor", "claude"])
        # 上限の係は休ませる
        provs2, calls2 = self.fake({})
        with mock.patch.dict(flat.PROVIDERS, provs2):
            res2 = flat.generate("hi", interactive=True)
        self.assertEqual(res2.provider, "cursor")
        self.assertEqual(calls2, ["cursor"])

    def test_all_fail_raises_without_metered(self):
        provs, _ = self.fake({k: "fail" for k in flat.PROVIDERS})
        with mock.patch.dict(flat.PROVIDERS, provs):
            with self.assertRaises(flat.FlatAIError):
                flat.generate("hi")

    def test_genspark_floor(self):
        with mock.patch.object(flat, "genspark_exe", return_value="/x/gsk"), \
             mock.patch.object(flat, "genspark_credits", return_value=499):
            with self.assertRaises(flat.LimitReached):
                flat.gen_gencode("hi", timeout=10)
        with mock.patch.object(flat, "genspark_exe", return_value="/x/gsk"), \
             mock.patch.object(flat, "genspark_credits", return_value=None):
            with self.assertRaises(RuntimeError):
                flat.gen_gencode("hi", timeout=10)

    def test_gencode_once_per_process(self):
        with mock.patch.object(flat, "genspark_exe", return_value="/x/gsk"), \
             mock.patch.object(flat, "genspark_credits", return_value=5000), \
             mock.patch.object(flat, "_run", return_value='{"result": {"answer": "done"}}'):
            self.assertEqual(flat.gen_gencode("hi", timeout=10), "done")
            with self.assertRaises(RuntimeError):
                flat.gen_gencode("hi", timeout=10)

    def test_env_drops_metered_keys(self):
        with mock.patch.dict("os.environ", {"ANTHROPIC_API_KEY": "x", "GEMINI_API_KEY": "y", "OPENAI_API_KEY": "z"}):
            env = flat._env()
        for k in ("ANTHROPIC_API_KEY", "GEMINI_API_KEY", "OPENAI_API_KEY"):
            self.assertNotIn(k, env)

    def test_generate_json(self):
        provs, _ = self.fake({})
        provs["codex"] = lambda p, *, timeout, images=(): 'note\n{"a": 1}\n'
        with mock.patch.dict(flat.PROVIDERS, provs):
            obj, res = flat.generate_json("x", interactive=True)
        self.assertEqual(obj, {"a": 1})


if __name__ == "__main__":
    unittest.main()
