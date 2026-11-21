"""FlowForge 入力プログラムの差分計算（ブラウザ不要の部分だけ）。"""
import importlib.util
import unittest
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "ff_paste", Path(__file__).resolve().parents[1] / "jarvis_flowforge_assistant_paste.py"
)
ff = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ff)


class DiffTests(unittest.TestCase):
    def test_list_diff_counts_duplicates(self):
        added, removed = ff.list_diff(["a → b", "a → b", "b → c"], ["a → b", "c → d"])
        assert added == ["c → d"]
        assert removed == ["a → b", "b → c"]

    def test_diff_states_reports_unrequested_changes(self):
        before = {"nodes": 3, "updatedAt": "t1", "edges": ["A → 合流"], "titles": ["A", "B", "合流"]}
        after = {"nodes": 3, "updatedAt": "t2", "edges": ["B → 合流", "X → Y"], "titles": ["A", "B", "合流"]}
        d = ff.diff_states(before, after)
        assert d["changed"] is True
        assert d["edges_added"] == ["B → 合流", "X → Y"]
        assert d["edges_removed"] == ["A → 合流"]
        assert d["nodes_added"] == [] and d["nodes_removed"] == []

    def test_diff_states_unchanged(self):
        s = {"nodes": 1, "updatedAt": "t1", "edges": [], "titles": ["A"]}
        d = ff.diff_states(s, dict(s))
        assert d["changed"] is False and d["edges_added"] == [] and d["edges_removed"] == []


class FlowIdForAgentTests(unittest.TestCase):
    """Mac 側の待ち箱・直接編集が開くフロー（315=315-A、315-B=別フロー）。"""

    def test_315_is_a_and_315b_is_b(self):
        assert ff.flow_id_for_agent("315") == "flow_S5g_i7CCiE0P6RKIp2_MkMTA"
        assert ff.flow_id_for_agent("315-B") == "flow_qJcURKdC36ARzDdSwEfLisvt"

    def test_other_agent_unchanged(self):
        assert ff.flow_id_for_agent("316") == "flow_TA9fHAyKHFlfTFb8fvpDG6Nh"

    def test_unregistered_still_errors(self):
        with self.assertRaises(SystemExit):
            ff.flow_id_for_agent("315-C")
        with self.assertRaises(SystemExit):
            ff.flow_id_for_agent("999")


if __name__ == "__main__":
    unittest.main()
