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


if __name__ == "__main__":
    unittest.main()
