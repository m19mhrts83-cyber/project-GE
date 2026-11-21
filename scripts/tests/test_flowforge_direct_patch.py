"""FlowForge 直接編集の計画と検証（ブラウザ不要）。311 と同じ形の見本フローで確かめる。"""
import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import jarvis_flowforge_direct_patch as dp  # noqa: E402


def n(id_, kind, title, parent=None, x=0, y=0, desc=""):
    return {"id": id_, "parentId": parent, "kind": kind, "subtype": None, "title": title,
            "description": desc, "meta": "", "toolName": "", "x": x, "y": y}


def make_snap():
    """入口A/B → 合流 → サブフロー（中に4ノード）→ 終了。B と NG は孤立。"""
    return {
        "nodes": [
            n("start", "start", "開始"),
            n("A", "tool", "入口A"),
            n("B", "tool", "入口B"),
            n("M", "tool", "合流"),
            n("S", "subflow", "点検"),
            n("s1", "tool", "読み込み", "S"),
            n("s2", "claude", "判定", "S"),
            n("ok", "tool", "OK通知", "S"),
            n("ng", "tool", "NG通知", "S"),
            n("end", "end", "終了"),
        ],
        "edges": [
            {"id": "e1", "source": "start", "target": "A"},
            {"id": "e2", "source": "A", "target": "M"},
            {"id": "e3", "source": "M", "target": "S"},
            {"id": "e4", "source": "s1", "target": "s2"},
            {"id": "e5", "source": "s2", "target": "ok"},
            {"id": "e6", "source": "S", "target": "end"},
        ],
    }


def pairs(s):
    return sorted((e["source"], e["target"]) for e in s["edges"])


class DirectPatchTests(unittest.TestCase):
    # --- 受入条件: 説明文だけを更新した場合、ノードと矢印が一切変わらない ---
    def test_description_only_keeps_structure(self):
        snap = make_snap()
        plan = dp.plan_patch(snap, [
            {"op": "update_node", "id": "B", "patch": {"description": "CLI 直接"}},
            {"op": "update_node", "id": "s2", "patch": {"description": "OK／NG を確定"}},
        ])
        assert pairs(plan["expected"]) == pairs(snap)
        assert [x["id"] for x in plan["expected"]["nodes"]] == [x["id"] for x in snap["nodes"]]
        assert all(s["op"] == "update_node" for s in plan["steps"])
        # 孤立ノード B を更新しても、つなぐ手順は一切入らない
        assert dp.summarize_change(snap, plan["expected"])["edges_added"] == []

    # --- 受入条件: 矢印1本の追加で、既存の接続が消えない ---
    def test_add_edge_that_would_displace_is_refused(self):
        snap = make_snap()
        with self.assertRaises(dp.PatchError) as e:
            dp.plan_patch(snap, [{"op": "add_edge", "source": "B", "target": "M"}])
        assert "入口A → 合流" in str(e.exception)
        assert "replace=true" in str(e.exception)

    def test_add_edge_without_conflict_adds_exactly_one(self):
        snap = make_snap()
        plan = dp.plan_patch(snap, [{"op": "add_edge", "source": "ok", "target": "ng"}])
        assert set(pairs(plan["expected"])) - set(pairs(snap)) == {("ok", "ng")}
        assert set(pairs(snap)) - set(pairs(plan["expected"])) == set()
        assert plan["steps"] == [{"op": "add_edge", "source": "ok", "target": "ng", "replaces": []}]

    def test_add_edge_with_replace_removes_only_the_named_conflict(self):
        snap = make_snap()
        plan = dp.plan_patch(snap, [{"op": "add_edge", "source": "B", "target": "M", "replace": True}])
        assert set(pairs(snap)) - set(pairs(plan["expected"])) == {("A", "M")}
        assert set(pairs(plan["expected"])) - set(pairs(snap)) == {("B", "M")}
        assert plan["steps"][0]["replaces"] == ["e2"]

    def test_edge_crossing_subflow_attaches_to_subflow(self):
        snap = make_snap()
        """サブフローの中から外へ引くと、矢印はサブフローそのものに付く（S → end と衝突する）。"""
        with self.assertRaises(dp.PatchError):
            dp.plan_patch(snap, [{"op": "add_edge", "source": "ng", "target": "end"}])

    def test_inner_edges_do_not_conflict_with_outer_edges(self):
        snap = make_snap()
        assert dp.edge_conflicts(snap, "ok", "ng") == []
        assert [e["id"] for e in dp.edge_conflicts(snap, "s1", "ok")] == ["e4", "e5"]

    def test_invalid_requests_change_nothing(self):
        snap = make_snap()
        before = copy.deepcopy(snap)
        bad = [
            [],
            [{"op": "update_node", "id": "nope", "patch": {"title": "x"}}],
            [{"op": "update_node", "id": "A", "patch": {"kind": "human"}}],
            [{"op": "update_node", "id": "A", "patch": {"title": "  "}}],
            [{"op": "add_edge", "source": "A", "target": "start"}],
            [{"op": "add_edge", "source": "end", "target": "A"}],
            [{"op": "add_edge", "source": "s1", "target": "S"}],
            [{"op": "remove_edge", "source": "B", "target": "M"}],
            [{"op": "delete_node", "id": "A"}],
            # 1件目は正しくても、2件目がだめなら全体を止める
            [{"op": "update_node", "id": "A", "patch": {"title": "ok"}}, {"op": "remove_edge", "id": "zzz"}],
        ]
        for ops in bad:
            with self.assertRaises(dp.PatchError):
                dp.plan_patch(snap, ops)
        assert snap == before  # 入力は書き換えない

    def test_duplicate_edge_is_a_noop(self):
        snap = make_snap()
        with self.assertRaises(dp.PatchError) as e:
            dp.plan_patch(snap, [{"op": "add_edge", "source": "A", "target": "M"}])
        assert "すでにある矢印" in str(e.exception)

    def test_remove_then_add_in_one_request(self):
        snap = make_snap()
        plan = dp.plan_patch(snap, [
            {"op": "remove_edge", "id": "e2"},
            {"op": "add_edge", "source": "B", "target": "M"},
        ])
        assert ("B", "M") in pairs(plan["expected"]) and ("A", "M") not in pairs(plan["expected"])
        assert plan["steps"][1]["replaces"] == []

    # --- 受入条件: 指示外の差分を確実に検知できる ---
    def test_compare_detects_unrequested_changes(self):
        snap = make_snap()
        plan = dp.plan_patch(snap, [{"op": "update_node", "id": "B", "patch": {"description": "x"}}])
        ok = copy.deepcopy(plan["expected"])
        assert dp.compare_to_expected(plan["expected"], ok) == []

        extra_edge = copy.deepcopy(ok)
        extra_edge["edges"].append({"id": "auto", "source": "ok", "target": "ng"})
        assert any("余分に増えた" in d for d in dp.compare_to_expected(plan["expected"], extra_edge))

        lost_edge = copy.deepcopy(ok)
        lost_edge["edges"] = [e for e in lost_edge["edges"] if e["id"] != "e2"]
        assert any("足りない" in d for d in dp.compare_to_expected(plan["expected"], lost_edge))

        moved = copy.deepcopy(ok)
        moved["nodes"][1]["x"] = 999  # 自動整列で位置が動いた
        assert any("x" in d for d in dp.compare_to_expected(plan["expected"], moved))

        other_text = copy.deepcopy(ok)
        other_text["nodes"][3]["title"] = "勝手に変わった"
        assert dp.compare_to_expected(plan["expected"], other_text)

        gone = copy.deepcopy(ok)
        gone["nodes"].pop()
        assert any("消えた" in d for d in dp.compare_to_expected(plan["expected"], gone))

    # --- 受入条件: 異常時は元の状態に安全に戻せる（戻せたかの判定） ---
    def test_same_state_is_strict(self):
        snap = make_snap()
        assert dp.same_state(snap, copy.deepcopy(snap))
        changed = copy.deepcopy(snap)
        changed["edges"][0]["id"] = "other"  # 同じ始点・終点でも、作り直された矢印は「同じ」としない
        assert not dp.same_state(snap, changed)

    def test_js_builders_embed_ids_safely(self):
        js = dp.js_apply('flow_"x', [{"op": "update_node", "id": "a", "patch": {"description": "改行\n「引用」'\""}}], "ラベル")
        assert "</script>" not in js and "__ffApi" in js
        assert dp.js_snapshot("flow_1").count("flow_1") == 1


class StaleTabTests(unittest.TestCase):
    def test_same_is_fresh(self):
        m = {"flow_a": "t1", "flow_b": "t2"}
        self.assertEqual(dp.stale_reasons(m, dict(m)), [])

    def test_tab_does_not_know_a_stored_flow(self):
        r = dp.stale_reasons({"flow_a": "t1"}, {"flow_a": "t1", "flow_b": "t2"})
        self.assertEqual(len(r), 1)
        self.assertIn("知らないフロー", r[0])

    def test_other_flow_was_edited_elsewhere(self):
        """311 のタブが、別のタブで直した 312 の古い内容を持っている（上書きの危険）。"""
        r = dp.stale_reasons({"flow_311": "t1", "flow_312": "old"}, {"flow_311": "t1", "flow_312": "new"})
        self.assertEqual(len(r), 1)
        self.assertIn("flow_312", r[0])

    def test_flow_only_in_tab(self):
        r = dp.stale_reasons({"flow_a": "t1", "flow_gone": "t9"}, {"flow_a": "t1"})
        self.assertIn("このタブにだけある", r[0])

    def test_js_freshness_reads_only(self):
        js = dp.js_freshness()
        self.assertIn("localStorage.getItem", js)
        # 書き込みの呼び出しが無いこと（typeof v.setState の判定は呼び出しではない）
        for call in ("setItem(", ".setState(", "updateNodeData(", "addEdge(", "removeEdge(", "deleteFlow(", ".undo("):
            self.assertNotIn(call, js)


if __name__ == "__main__":
    unittest.main()

class CreationTests(unittest.TestCase):
    def flow(self):
        return {"id": "flow_test12345", "name": "Synthetic workflow", "description": "test", "nodes": [
            {"id":"start", "kind":"start", "title":"Start", "x":0, "y":0},
            {"id":"end", "kind":"end", "title":"End", "x":200, "y":0}],
            "edges":[{"id":"e", "source":"start", "target":"end"}]}

    def test_create_and_native_shape(self):
        f = dp.validate_flow(self.flow())
        native = dp.native_flow(f)
        self.assertEqual(native["nodes"][0]["data"]["kind"], "start")
        self.assertEqual(native["nodes"][0]["position"], {"x":0,"y":0})

    def test_rejects_duplicate_ids_invalid_parent_branch_and_cycle(self):
        import copy
        f = self.flow(); f["nodes"].append(dict(f["nodes"][0]))
        with self.assertRaises(dp.PatchError): dp.validate_flow(f)
        f = self.flow(); f["nodes"][1]["parentId"] = "missing"
        with self.assertRaises(dp.PatchError): dp.validate_flow(f)
        f = self.flow(); f["nodes"].append({"id":"x","kind":"tool","title":"X","x":1,"y":1})
        f["edges"].append({"id":"e2","source":"start","target":"x"})
        with self.assertRaises(dp.PatchError): dp.validate_flow(f)
        f = self.flow(); f["nodes"][0]["x"] = float("nan")
        with self.assertRaises(dp.PatchError): dp.validate_flow(f)

    def test_add_node_is_exact_and_does_not_connect(self):
        f = dp.validate_flow(self.flow())
        n = {"id":"n","kind":"tool","subtype":"api","title":"Card","x":100,"y":0}
        p = dp.plan_patch(f, [{"op":"add_node", "node":n}])
        self.assertEqual(p["expected"]["edges"], f["edges"])
        self.assertEqual(p["expected"]["nodes"][-1], n)
        with self.assertRaises(dp.PatchError):
            dp.plan_patch(p["expected"], [{"op":"add_node","node":n}])
        p = dp.plan_patch(f,[{"op":"add_node","node":n}, {"op":"remove_edge","id":"e"},
            {"op":"add_edge","source":"start","target":"n"},{"op":"add_edge","source":"n","target":"end"}])
        self.assertEqual(len(p["expected"]["edges"]),2)

class NodeRemovalTests(unittest.TestCase):
    def test_removal_requires_explicit_edges_and_children(self):
        snap=make_snap()
        with self.assertRaises(dp.PatchError):dp.plan_patch(snap,[{'op':'remove_node','id':'start'}])
        with self.assertRaises(dp.PatchError):dp.plan_patch(snap,[{'op':'remove_node','id':'missing'}])
        node={'id':'x','kind':'tool','title':'X','x':0,'y':0}
        p=dp.plan_patch({'nodes':[node],'edges':[]},[{'op':'remove_node','id':'x'}])
        self.assertEqual(p['expected']['nodes'],[])
        with self.assertRaises(dp.PatchError):dp.plan_patch({'nodes':[node],'edges':[{'id':'e','source':'x','target':'y'}]},[{'op':'remove_node','id':'x'}])
        parent={'id':'p','kind':'subflow','title':'P','x':0,'y':0}
        with self.assertRaises(dp.PatchError):dp.plan_patch({'nodes':[parent,{**node,'parentId':'p'}],'edges':[]},[{'op':'remove_node','id':'p'}])
