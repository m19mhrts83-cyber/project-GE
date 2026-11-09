import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import jarvis_dispatch_launch as L

OWNER = L.OWNER_USER


def rec(*items):
    return {"id": "20261110-0100", "items": [{"no": i + 1, **it} for i, it in enumerate(items)]}


IMPL = {"title": "317 の改善を実装", "agent": "claude_code", "mode": "rule", "kind": "implement", "notes": [],
        "request_text": "ミスレモンへ: ...", "path": "docs/x/TASK.md"}


class ApprovalTests(unittest.TestCase):
    def test_parse_numbers_override_and_reject(self):
        a = L.parse_approval(["1と3OK、2はCodexで、4はなし"], 4)
        self.assertEqual(a[1], {"ok": True, "agent": None})
        self.assertEqual(a[3], {"ok": True, "agent": None})
        self.assertEqual(a[2], {"ok": True, "agent": "codex"})
        self.assertFalse(a[4]["ok"])

    def test_fullwidth_and_all(self):
        self.assertTrue(L.parse_approval(["１、２ お願い"], 2)[2]["ok"])
        self.assertEqual(set(L.parse_approval(["全部OK"], 3)), {1, 2, 3})

    def test_only_owner_counts_and_reply_overrides_reaction(self):
        reactions = [{"name": "white_check_mark", "users": ["USOMEONE"]}]
        self.assertEqual(L.approvals_from(reactions, [], 2), {})
        reactions = [{"name": "white_check_mark", "users": [OWNER]}]
        replies = [{"user": OWNER, "text": "2は待って"}, {"user": "UOTHER", "text": "1はなし"}]
        a = L.approvals_from(reactions, replies, 2)
        self.assertTrue(a[1]["ok"])
        self.assertFalse(a[2]["ok"])


class PlanTests(unittest.TestCase):
    def setUp(self):
        os.environ["JARVIS_DISPATCH_LAUNCH_MAX"] = "2"

    def test_safety_and_kinds(self):
        r = rec(IMPL,
                {**IMPL, "title": "振込の準備", "kind": "money", "agent": "cursor"},
                {**IMPL, "title": "業者へ返信", "notes": ["対外送信あり。送信は松野さんの了承"], "agent": "codex"},
                {**IMPL, "title": "フロー整理", "agent": "chatgpt_mode", "kind": "design"},
                {**IMPL, "title": "111", "mode": "keep", "agent": "codex"})
        ok = {n: {"ok": True, "agent": None} for n in range(1, 6)}
        acts = {a["no"]: a for a in L.plan(r, ok, {}, running=0)}
        self.assertEqual(acts[1]["do"], "launch")
        self.assertEqual(acts[2]["do"], "reply")   # お金
        self.assertEqual(acts[3]["do"], "reply")   # 対外送信
        self.assertEqual(acts[4]["do"], "reply")   # チャッピーは自動不可
        self.assertIn("依頼文", acts[4]["why"])
        self.assertEqual(acts[5]["do"], "skip")    # 現担当のまま

    def test_cap_dedupe_and_override(self):
        r = rec(IMPL, IMPL, IMPL)
        ok = {1: {"ok": True, "agent": None}, 2: {"ok": True, "agent": "codex"}, 3: {"ok": True, "agent": None}}
        acts = L.plan(r, ok, {}, running=1)
        self.assertEqual([a["do"] for a in acts], ["launch", "wait", "wait"])
        acts = L.plan(r, ok, {"handled": {"20261110-0100#1": {}}}, running=0)
        self.assertEqual([(a["no"], a["do"], a.get("agent")) for a in acts],
                         [(2, "launch", "codex"), (3, "launch", "claude_code")])

    def test_unapproved_is_ignored(self):
        self.assertEqual(L.plan(rec(IMPL), {}, {}, running=0), [])


class CommandTests(unittest.TestCase):
    def test_prompt_forbids_main_and_merge(self):
        p = L.agent_prompt(IMPL, L.branch_name("20261110-0100#1"))
        self.assertIn("dispatch/20261110-0100-1", p)
        self.assertIn("--draft", p)
        self.assertIn("main への push", p)
        self.assertIn("マージ", p)

    def test_commands(self):
        c = L.launch_cmd("codex", Path("/tmp/w"), "x")
        self.assertEqual(c[:2], ["codex", "exec"])
        c = L.launch_cmd("claude_code", Path("/tmp/w"), "x")
        self.assertEqual(c[:2], ["claude", "-p"])
        self.assertNotIn("--dangerously-skip-permissions", c)

    def test_real_launch_needs_enable_flag(self):
        os.environ.pop("JARVIS_DISPATCH_LAUNCH_ENABLE", None)
        self.assertFalse(L._flag("JARVIS_DISPATCH_LAUNCH_ENABLE"))


if __name__ == "__main__":
    unittest.main()
