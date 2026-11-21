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
        assert ff.flow_id_for_agent("315-B") == "flow_ZQIfYZY4GJF2XspXY8i0sGWD"

    def test_other_agent_unchanged(self):
        assert ff.flow_id_for_agent("316") == "flow_TA9fHAyKHFlfTFb8fvpDG6Nh"

    def test_unregistered_still_errors(self):
        with self.assertRaises(SystemExit):
            ff.flow_id_for_agent("315-C")
        with self.assertRaises(SystemExit):
            ff.flow_id_for_agent("999")


if __name__ == "__main__":
    unittest.main()

class DirectCreateTests(unittest.TestCase):
    def test_existing_id_and_stale_tab_do_not_write(self):
        from unittest.mock import patch
        import jarvis_flowforge_assistant_paste as ff
        import jarvis_flowforge_migrate_to_home as mg
        import jarvis_flowforge_direct_patch as dp
        f={"id":"flow_test12345","name":"Synthetic","nodes":[
           {"id":"start","kind":"start","title":"Start","x":0,"y":0},
           {"id":"end","kind":"end","title":"End","x":10,"y":0}],
           "edges":[{"id":"e","source":"start","target":"end"}]}
        with patch.object(mg,'home_tab',return_value=(1,1)),patch.object(mg,'list_flows',return_value=[{'id':f['id']}]),patch.object(ff,'run_main') as write:
            with self.assertRaises(dp.PatchError):ff.direct_create(f)
            write.assert_not_called()
        with patch.object(mg,'home_tab',return_value=(1,1)),patch.object(mg,'list_flows',return_value=[]),patch.object(ff,'tab_freshness',return_value=['stale']),patch.object(ff,'run_main') as write:
            with self.assertRaises(dp.PatchError):ff.direct_create(f)
            write.assert_not_called()

class VerificationTests(unittest.TestCase):
    def test_cloud_failure_is_not_verified_even_when_local_matches(self):
        import json
        from pathlib import Path
        from unittest.mock import patch
        import jarvis_flowforge_assistant_paste as ff
        import jarvis_flowforge_migrate_to_home as mg
        f={"id":"flow_test12345","name":"Synthetic","description":"test","nodes":[
           {"id":"start","kind":"start","title":"Start","x":0,"y":0},
           {"id":"end","kind":"end","title":"End","x":10,"y":0}],
           "edges":[{"id":"e","source":"start","target":"end"}]}
        actual={**f,'updatedAt':'test'}
        with patch.object(mg,'home_tab',return_value=(1,1)),patch.object(mg,'list_flows',return_value=[]),patch.object(ff,'tab_freshness',return_value=[]),patch.object(ff,'backup_store',return_value=Path('/synthetic/backup')),patch.object(ff,'other_flow_diffs',return_value=[]),patch.object(ff,'run_main',return_value=json.dumps({'ok':True,'snap':actual})),patch.object(ff,'sync_owned',return_value={'ok':False,'status':403,'detail':'flow_owner_mismatch'}):
            r=ff.direct_create(f)
            self.assertTrue(r['local_verified']);self.assertFalse(r['verified'])

    def test_patch_unexpected_change_undoes_and_checks_restoration(self):
        import json
        from pathlib import Path
        from unittest.mock import patch
        import jarvis_flowforge_assistant_paste as ff
        before={'nodes':[{'id':'start','kind':'start','title':'Start','x':0,'y':0}], 'edges':[], 'updatedAt':'old'}
        wrong={'nodes':[{'id':'start','kind':'start','title':'Unasked','x':0,'y':0}], 'edges':[], 'updatedAt':'new','historyTop':ff.dp.HISTORY_LABEL}
        replies=[json.dumps({'ok':True,'snap':wrong}),json.dumps({'ok':True,'snap':before})]
        with patch.object(ff,'prepare',return_value=((1,1),{})),patch.object(ff,'read_store',return_value=before),patch.object(ff,'backup_store',return_value=Path('/synthetic/backup')),patch.object(ff,'other_flow_diffs',return_value=[]),patch.object(ff,'run_main',side_effect=replies),patch.object(ff,'wait_sync',return_value='saved'),patch.object(ff,'reload_other_editor_tabs',return_value=0):
            r=ff.direct_patch('flow_test',[{'op':'update_node','id':'start','patch':{'title':'Expected'}}])
            self.assertFalse(r['verified']);self.assertTrue(r['rolled_back'])
