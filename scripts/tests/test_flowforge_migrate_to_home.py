"""FlowForge を置き場へ移すスクリプトの、照合と登録の付け替え（ブラウザ不要の部分）。"""
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import jarvis_flowforge_migrate_to_home as mg  # noqa: E402


def share_nodes():
    """共有リンクの形（data の中に項目がある。位置つき）。"""
    return [
        {"id": "start", "position": {"x": 0, "y": 0}, "data": {"kind": "start", "title": "開始", "description": "毎日"}},
        {"id": "s", "position": {"x": 1, "y": 1}, "data": {"kind": "subflow", "title": "点検"}},
        {"id": "a", "parentId": "s", "position": {"x": 2, "y": 2}, "data": {"kind": "tool", "title": "読む", "toolName": "GWS"}},
        {"id": "end", "position": {"x": 3, "y": 3}, "data": {"kind": "end", "title": "終了"}},
    ]


EDGES = [{"id": "e1", "source": "start", "target": "s"}, {"id": "e2", "source": "s", "target": "end"}]


class ContentTests(unittest.TestCase):
    def test_copy_with_moved_positions_and_new_edge_ids_is_same(self):
        src = mg.normalize(share_nodes(), EDGES)
        copied = share_nodes()
        for n in copied:
            n["position"] = {"x": 99, "y": 99}
        dst = mg.normalize(copied, [{"id": "other", "source": "start", "target": "s"}, {"id": "x", "source": "s", "target": "end"}])
        self.assertEqual(mg.content_diffs(src, dst), [])

    def test_detects_missing_node_changed_text_and_edges(self):
        src = mg.normalize(share_nodes(), EDGES)
        broken = share_nodes()[:-1]
        broken[0]["data"]["description"] = "変わった"
        dst = mg.normalize(broken, EDGES[:1] + [{"id": "z", "source": "a", "target": "start"}])
        diffs = mg.content_diffs(src, dst)
        self.assertTrue(any("コピーに無いノード" in d for d in diffs))
        self.assertTrue(any("description" in d for d in diffs))
        self.assertTrue(any("コピーに無い矢印" in d for d in diffs))
        self.assertTrue(any("コピーにだけある矢印" in d for d in diffs))

    def test_detects_parent_change(self):
        src = mg.normalize(share_nodes(), EDGES)
        moved = share_nodes()
        del moved[2]["parentId"]
        self.assertTrue(any("parentId" in d for d in mg.content_diffs(src, mg.normalize(moved, EDGES))))


class ShareConfigTests(unittest.TestCase):
    def test_rewrite_sets_agent_and_adds_flow_keeps_others(self):
        before = json.dumps({
            "updated": "x",
            "by_flow_id": {"flow_old": "https://h/share/OLD", "flow_other": "https://h/share/OTHER"},
            "by_agent_id": {"315": "https://h/share/OLD", "312": "https://h/share/OTHER"},
        })
        after = json.loads(mg.rewrite_share_config(before, "315", "flow_new", "https://h/share/NEW"))
        self.assertEqual(after["by_agent_id"]["315"], "https://h/share/NEW")
        self.assertEqual(after["by_agent_id"]["312"], "https://h/share/OTHER")
        self.assertEqual(after["by_flow_id"]["flow_new"], "https://h/share/NEW")
        # 元のフローの行は消さない（元は持ち主のブラウザに残っている）
        self.assertEqual(after["by_flow_id"]["flow_old"], "https://h/share/OLD")
        self.assertEqual(after["updated"], "x")


class RewriteScopeTests(unittest.TestCase):
    def test_past_records_are_not_rewritten(self):
        self.assertTrue(mg.should_rewrite(("300_室", "315_係", "README.md")))
        self.assertTrue(mg.should_rewrite(("00_チーム索引.md",)))
        self.assertFalse(mg.should_rewrite(("300_室", "315_係", "logs", "20261011_ops_health.md")))
        self.assertFalse(mg.should_rewrite(("300_室", "315_係", "output", "report.md")))
        self.assertFalse(mg.should_rewrite(("memory", "MEMORY.md")))
        # ファイル名が logs.md でも、フォルダでなければ対象
        self.assertTrue(mg.should_rewrite(("300_室", "logs.md")))


if __name__ == "__main__":
    unittest.main()
