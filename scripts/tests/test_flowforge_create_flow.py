"""FlowForge 新規作成 CLI（画面操作はモック）。Chrome・待ち箱・共有 API には触らない。"""
import contextlib
import copy
import json
import os
import stat
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import jarvis_flowforge_assistant_paste as ff  # noqa: E402
import jarvis_flowforge_create_flow as cf  # noqa: E402
import jarvis_flowforge_direct_patch as dp  # noqa: E402
import jarvis_flowforge_migrate_to_home as mg  # noqa: E402

BASE = cf.BASE
NEW_ID = "flow_NEWnewNEWnew0001"


def native(flat):
    """平らな形 → FlowForge の保存形。"""
    out = {k: flat[k] for k in ("id", "name", "description", "createdAt", "updatedAt") if k in flat}
    out["nodes"] = []
    for n in flat["nodes"]:
        node = {"id": n["id"], "position": {"x": n.get("x", 0), "y": n.get("y", 0)},
                "data": {k: v for k, v in n.items() if k not in {"id", "parentId", "x", "y", "width", "height"} and v not in (None, "")}}
        if n.get("parentId"):
            node["parentId"] = n["parentId"]
        out["nodes"].append(node)
    out["edges"] = [{"id": e["id"], "source": e["source"], "target": e["target"]} for e in flat["edges"]]
    return out


def flat(nat):
    nodes = []
    for n in nat["nodes"]:
        d = n.get("data") or {}
        nodes.append({"id": n["id"], "parentId": n.get("parentId"), "kind": d.get("kind"), "subtype": d.get("subtype"),
                      "title": d.get("title", ""), "description": d.get("description", ""), "meta": d.get("meta", ""),
                      "toolName": d.get("toolName", ""), "x": n["position"]["x"], "y": n["position"]["y"]})
    return {"id": nat["id"], "name": nat.get("name"), "description": nat.get("description", ""),
            "updatedAt": nat.get("updatedAt"), "historyTop": dp.HISTORY_LABEL,
            "nodes": nodes, "edges": [dict(e) for e in nat["edges"]]}


def generated(created_at):
    """生成AIが作りそうな形（開始・サブフロー3子・人・終了）。"""
    def node(i, kind, title, parent=None, x=0, y=0, subtype=None):
        return {"id": i, "kind": kind, "title": title, "parentId": parent, "x": x, "y": y, "subtype": subtype}
    return native({
        "id": NEW_ID, "name": "生成された名前", "description": "生成された説明", "createdAt": created_at, "updatedAt": created_at,
        "nodes": [node("start", "start", "毎朝9:00に起動"), node("sub1", "subflow", "取得", x=260),
                  node("n1", "tool", "取得", "sub1", 16, 60, "mcp"), node("n2", "claude", "要約", "sub1", 16, 192, "think"),
                  node("n3", "tool", "ラベル", "sub1", 16, 324, "mcp"), node("h1", "human", "確認", x=552, subtype="human"),
                  node("end", "end", "通知", x=812)],
        "edges": [{"id": "g1", "source": "start", "target": "sub1"}, {"id": "g2", "source": "n1", "target": "n2"},
                  {"id": "g3", "source": "n2", "target": "n3"}, {"id": "g4", "source": "sub1", "target": "h1"},
                  {"id": "g5", "source": "h1", "target": "end"}],
    })


PLAN = {
    "name": "テスト用：朝の確認",
    "description": "確定した説明",
    "nodes": [
        {"id": "s", "kind": "start", "title": "毎朝起動", "description": "手動でも可"},
        {"id": "read", "kind": "tool", "subtype": "mcp", "title": "メールを読む"},
        {"id": "pick", "kind": "claude", "subtype": "think", "title": "要点を選ぶ"},
        {"id": "ok", "kind": "human", "subtype": "human", "title": "本人が確かめる"},
        {"id": "e", "kind": "end", "title": "Slack へ送る"},
    ],
    "edges": [{"id": "p1", "source": "s", "target": "read"}, {"id": "p2", "source": "read", "target": "pick"},
              {"id": "p3", "source": "pick", "target": "ok"}, {"id": "p4", "source": "ok", "target": "e"}],
}

OTHER = native({"id": "flow_OTHERotherOTHER01", "name": "既存", "description": "", "createdAt": "2026-11-01T00:00:00Z",
                "updatedAt": "2026-11-01T00:00:00Z",
                "nodes": [{"id": "start", "kind": "start", "title": "開始"}, {"id": "end", "kind": "end", "title": "終了"}],
                "edges": [{"id": "x1", "source": "start", "target": "end"}]})


class FakeChrome:
    def __init__(self, generate_after=2, generate=True):
        self.flows = {OTHER["id"]: copy.deepcopy(OTHER)}
        self.urls = {(1, 10): BASE + "/", (1, 11): BASE + "/flows/" + OTHER["id"], (1, 12): BASE + "/share/abc"}
        self.unreadable = set()
        self.clicks = 0
        self.filled = ""
        self.polls_after_click = None
        self.generate_after, self.generate = generate_after, generate
        self.observed = []
        self.share_clicks = 0
        self.sync_text = "クラウド同期済"
        self.calls = []

    def tabs(self):
        return [t for t, u in self.urls.items() if u.startswith(BASE)]

    def url(self, tab):
        return self.urls[tab]

    def _tick(self):
        if self.polls_after_click is None or not self.generate:
            return
        self.polls_after_click += 1
        if self.polls_after_click == self.generate_after and NEW_ID not in self.flows:
            self.flows[NEW_ID] = generated(cf.now_iso())
            self.urls[(1, 10)] = BASE + "/flows/" + NEW_ID

    def js(self, tab, code):
        self.calls.append(("js", tab, code[:30]))
        if tab in self.unreadable or not self.urls[tab].startswith(BASE):
            raise RuntimeError("not allowed")
        if code == cf.JS_ALL_FLOWS:
            self._tick()
            return json.dumps({"ok": True, "flows": self.flows})
        if code == cf.JS_TOP_STATE:
            top = self.urls[tab].rstrip("/") == BASE
            return json.dumps({"path": "/", "textareas": 1 if top else 0, "button": 1 if top else 0,
                               "disabled": not self.filled})
        if "filled:" in code:
            self.filled = "x"
            return "filled:10"
        if code == cf.JS_TOP_CLICK:
            self.clicks += 1
            self.polls_after_click = 0
            return "clicked"
        if code == cf.JS_SKIP_OVERLAY:
            return "none"
        if code == ff.JS_SYNC_TEXT:
            return self.sync_text
        if code == mg.JS_CLICK_SHARE:
            self.share_clicks += 1
            return "clicked"
        if code == mg.JS_READ_SHARE:
            return BASE + "/share/SHAREid01"
        if code == mg.JS_CLOSE_DIALOG:
            return "closed"
        raise AssertionError("unexpected js " + code[:60])

    def main(self, tab, code):
        if code == cf.JS_OBSERVE:
            return "observer_ready"
        if code == cf.JS_OBSERVED:
            return json.dumps(self.observed)
        raise AssertionError("unexpected main js")

    def set_url(self, tab, url):
        self.calls.append(("set_url", tab, url))
        self.urls[tab] = url

    def reload(self, tab):
        self.calls.append(("reload", tab))

    def new_tab(self, win, url):
        t = (win, 99)
        self.urls[t] = url
        return t

    def open_home(self, url):
        self.urls[(1, 50)] = url

    def sleep(self, sec):
        time.sleep(0.001)


class FakeServices:
    def __init__(self, chrome):
        self.c = chrome
        self.queue_rows = []
        self.queue_error = None
        self.lock_ok = True
        self.patches = []
        self.sync_result = {"ok": True, "status": 200}
        self.share_override = None

    @contextlib.contextmanager
    def lock(self, wait):
        yield self.lock_ok

    def lock_holder(self):
        return {"holder": "queue"}

    def queue_active(self):
        if self.queue_error:
            raise self.queue_error
        return list(self.queue_rows)

    def freshness(self, tab):
        return []

    def read_store(self, tab, fid):
        return flat(self.c.flows[fid])

    def sync(self, tab, fid):
        return dict(self.sync_result)

    def direct_patch(self, fid, ops, tab):
        snap = flat(self.c.flows[fid])
        plan = dp.plan_patch(snap, ops)
        exp = plan["expected"]
        for i, e in enumerate(exp["edges"]):
            if e["id"].startswith("__new_"):
                e["id"] = f"made{len(self.patches)}_{i}"
        new = native({**snap, **exp, "id": fid, "createdAt": self.c.flows[fid].get("createdAt"),
                      "updatedAt": cf.now_iso()})
        self.c.flows[fid] = new
        self.patches.append(ops)
        return {"verified": True, "steps": len(plan["steps"])}

    def fetch_share(self, sid):
        if self.share_override is not None:
            return self.share_override
        return {"flow": copy.deepcopy(self.c.flows[NEW_ID])}


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ledger = cf.Ledger(Path(self.tmp.name) / "state" / "ledger.json")
        self.chrome = FakeChrome()
        self.svc = FakeServices(self.chrome)

    def tearDown(self):
        self.tmp.cleanup()

    def creator(self, **kw):
        kw.setdefault("generate_timeout", 2)
        kw.setdefault("queue_wait", 0)
        return cf.Creator(self.chrome, self.svc, self.ledger, backup_dir=Path(self.tmp.name) / "bk", **kw)


class FullRunTests(Base):
    def test_create_shape_share_verified(self):
        out = self.creator().run("テスト用：毎朝メールを確認\n", PLAN, agent="999")
        assert out["verified"] is True, out
        assert out["flow_id"] == NEW_ID and out["share_url"].endswith("/share/SHAREid01")
        assert self.chrome.clicks == 1 and self.chrome.share_clicks == 1
        assert out["diffs_before"] and out["diffs_after"] == []
        assert out["nodes"] == 5 and out["edges"] == 4 and out["name"] == PLAN["name"]
        assert out["other_flows_changed"] == []
        assert all(len(b) <= dp.MAX_OPS for b in self.svc.patches) and len(self.svc.patches) >= 2
        # 開始・終了は生成されたもの（ID）を使う
        ids = {n["id"] for n in self.chrome.flows[NEW_ID]["nodes"]}
        assert {"start", "end", "read", "pick", "ok"} == ids
        # 他の FlowForge タブは about:blank にして、最後に元の URL へ戻す
        assert ("set_url", (1, 11), "about:blank") in self.chrome.calls
        assert self.chrome.urls[(1, 11)] == BASE + "/flows/" + OTHER["id"]
        assert self.chrome.urls[(1, 12)] == BASE + "/share/abc"
        assert any("agents_registry.yaml の '999'" in s for s in out["next_steps"])
        entry = self.ledger.get(cf.text_key("テスト用：毎朝メールを確認"))
        assert entry["state"] == "verified" and entry["flow_id"] == NEW_ID and entry["parked_tabs"] == []
        assert "毎朝メール" not in self.ledger.path.read_text()  # 本文は台帳に残さない
        assert stat.S_IMODE(os.stat(self.ledger.path).st_mode) == 0o600
        assert stat.S_IMODE(os.stat(out["backup_path"]).st_mode) == 0o600

    def test_same_text_is_not_created_twice(self):
        self.creator().run("工程A", PLAN)
        again = self.creator().run("  工程A  \r\n", PLAN)
        assert again["already_done"] is True and self.chrome.clicks == 1

    def test_without_plan_keeps_generated_and_says_so(self):
        out = self.creator().run("工程B", None)
        assert out["verified"] is True and out["diffs_after"] is None and "note" in out
        assert self.svc.patches == []

    def test_new_plan_reshapes_same_flow_without_new_generation(self):
        self.creator().run("工程C", None)
        out = self.creator().run("工程C", PLAN)
        assert out["verified"] and self.chrome.clicks == 1 and out["flow_id"] == NEW_ID
        assert self.chrome.share_clicks == 1  # 共有リンクは前回のものを照合し直す


class StopTests(Base):
    def test_queue_busy_stops_before_anything(self):
        self.svc.queue_rows = [{"id": "q", "status": "running"}]
        with self.assertRaises(cf.CreateStop) as e:
            self.creator().run("工程", PLAN)
        assert e.exception.code == cf.EXIT_QUEUE and self.chrome.clicks == 0
        assert not any(c[0] == "set_url" for c in self.chrome.calls)

    def test_queue_unreadable_is_not_empty(self):
        self.svc.queue_error = SystemExit("JARVIS_SUPABASE_* 未設定")
        with self.assertRaises(cf.CreateStop) as e:
            self.creator().run("工程", PLAN)
        assert e.exception.code == cf.EXIT_QUEUE and self.chrome.clicks == 0

    def test_lock_held_by_other(self):
        self.svc.lock_ok = False
        with self.assertRaises(cf.CreateStop) as e:
            self.creator().run("工程", PLAN)
        assert e.exception.code == cf.EXIT_LOCK and self.chrome.clicks == 0

    def test_timeout_never_clicks_twice_and_resume_adopts(self):
        self.chrome.generate = False
        with self.assertRaises(cf.CreateStop) as e:
            self.creator(generate_timeout=0.05).run("工程D", PLAN)
        assert e.exception.code == cf.EXIT_GENERATE and self.chrome.clicks == 1
        entry = self.ledger.get(cf.text_key("工程D"))
        assert entry["state"] == "generate_clicked" and entry["last_stop"]["stage"] == "generate"
        # 止まった後で生成が終わっていた → 次の実行は押さずに引き継ぐ
        self.chrome.flows[NEW_ID] = generated(cf.now_iso())
        out = self.creator().run("工程D", PLAN)
        assert out["verified"] and self.chrome.clicks == 1 and out["flow_id"] == NEW_ID

    def test_clicked_but_nothing_made_needs_retry_flag(self):
        self.chrome.generate = False
        with self.assertRaises(cf.CreateStop):
            self.creator(generate_timeout=0.05).run("工程E", PLAN)
        with self.assertRaises(cf.CreateStop) as e:
            self.creator().run("工程E", PLAN)
        assert "--retry-generate" in str(e.exception) and self.chrome.clicks == 1
        self.chrome.generate, self.chrome.polls_after_click = True, None  # 1回目の押下では何もできなかった
        out = self.creator().run("工程E", PLAN, retry_generate=True)
        assert out["verified"] and self.chrome.clicks == 2

    def test_owner_mismatch_seen_stops_and_keeps_flow(self):
        self.chrome.observed = [{"status": 403, "error": "flow_owner_mismatch"}]
        with self.assertRaises(cf.CreateStop) as e:
            self.creator().run("工程F", PLAN)
        assert e.exception.stage == "sync" and e.exception.flow_id == NEW_ID
        assert NEW_ID in self.chrome.flows and self.svc.patches == []
        assert self.chrome.urls[(1, 11)] == BASE + "/flows/" + OTHER["id"]  # 止まってもタブは戻す

    def test_sync_api_failure_is_not_verified(self):
        self.svc.sync_result = {"ok": False, "status": 403, "detail": "flow_owner_mismatch"}
        with self.assertRaises(cf.CreateStop) as e:
            self.creator().run("工程G", PLAN)
        assert e.exception.stage == "sync"

    def test_share_mismatch_is_not_verified(self):
        self.svc.share_override = {"flow": {**generated("2026-11-22T00:00:00Z")}}
        with mock.patch.object(cf, "SHARE_CHECK_TRIES", 2):
            out = self.creator().run("工程H", PLAN)
        assert out["verified"] is False and out["share_check"]["ok"] is False
        assert self.ledger.get(cf.text_key("工程H"))["state"] == "unverified"

    def test_other_flow_changed_is_not_verified(self):
        orig = self.svc.direct_patch

        def patch_and_touch(fid, ops, tab):
            self.chrome.flows[OTHER["id"]]["name"] = "誰かが変えた"
            return orig(fid, ops, tab)
        self.svc.direct_patch = patch_and_touch
        out = self.creator().run("工程I", PLAN)
        assert out["verified"] is False and out["other_flows_changed"] == [OTHER["id"]]

    def test_shape_batch_not_verified_stops(self):
        self.svc.direct_patch = lambda fid, ops, tab: {"verified": False, "rolled_back": True, "unexpected": ["x"]}
        with self.assertRaises(cf.CreateStop) as e:
            self.creator().run("工程J", PLAN)
        assert e.exception.stage == "shape" and e.exception.code == cf.EXIT_UNVERIFIED

    def test_bad_plan_stops_after_create_with_flow_id(self):
        bad = {**PLAN, "edges": PLAN["edges"][:2]}  # 島ができる
        with self.assertRaises(cf.CreateStop) as e:
            self.creator().run("工程K", bad)
        assert e.exception.code == cf.EXIT_PLAN and e.exception.flow_id == NEW_ID and self.svc.patches == []

    def test_long_text_refused(self):
        with self.assertRaises(cf.CreateStop) as e:
            self.creator().run("あ" * (cf.MAX_TEXT + 1), PLAN)
        assert e.exception.code == cf.EXIT_PREFLIGHT and self.chrome.clicks == 0

    def test_no_readable_home_tab(self):
        self.chrome.unreadable = set(self.chrome.urls) | {(1, 50)}
        with self.assertRaises(cf.CreateStop) as e:
            self.creator().run("工程L", PLAN)
        assert e.exception.stage == "tab" and self.chrome.clicks == 0


class PureTests(unittest.TestCase):
    def test_text_key_ignores_outer_space_and_newlines(self):
        assert cf.text_key("a\r\nb  \n") == cf.text_key("  a\nb")
        assert cf.text_key("a\nb") != cf.text_key("a\nc")

    def test_corrupt_ledger_stops(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "l.json"
            p.write_text("{broken")
            with self.assertRaises(cf.CreateStop):
                cf.Ledger(p).get("k")

    def test_prepare_target_maps_start_end_and_positions(self):
        cur = flat(generated("2026-11-22T00:00:00Z"))
        t = cf.prepare_target(PLAN, cur)
        ids = [n["id"] for n in t["nodes"]]
        assert ids[0] == "start" and ids[-1] == "end" and t["id"] == NEW_ID
        assert next(n for n in t["nodes"] if n["id"] == "end")["x"] == 812  # 生成の位置のまま
        assert ("ok", "end") in [(e["source"], e["target"]) for e in t["edges"]]

    def test_shape_keeps_subflow_when_target_reuses_it(self):
        cur = flat(generated("2026-11-22T00:00:00Z"))
        plan = {"name": "x", "nodes": [
            {"id": "s", "kind": "start", "title": "開始"},
            {"id": "sub1", "kind": "subflow", "title": "取得"},
            {"id": "n1", "kind": "tool", "subtype": "mcp", "title": "取得し直す", "parentId": "sub1"},
            {"id": "n2", "kind": "claude", "subtype": "think", "title": "要約", "parentId": "sub1"},
            {"id": "e", "kind": "end", "title": "通知"}],
            "edges": [{"id": "a", "source": "s", "target": "sub1"}, {"id": "b", "source": "n1", "target": "n2"},
                      {"id": "c", "source": "sub1", "target": "e"}]}
        t = cf.prepare_target(plan, cur)
        ops = cf.shape_ops(cur, t)
        kinds = [o["op"] for o in ops]
        assert {"op": "remove_node", "id": "n3"} in ops and {"op": "remove_node", "id": "h1"} in ops
        assert "add_node" not in kinds
        assert {"op": "update_node", "id": "n1", "patch": {"title": "取得し直す"}} in ops
        cf.simulate(cur, cf.chunk_ops(ops), t)

    def test_simulate_detects_wrong_plan(self):
        cur = flat(generated("2026-11-22T00:00:00Z"))
        t = cf.prepare_target(PLAN, cur)
        ops = [o for o in cf.shape_ops(cur, t) if o["op"] != "update_flow"]
        with self.assertRaises(dp.PatchError):
            cf.simulate(cur, cf.chunk_ops(ops), t)

    def test_start_subtype_change_refused(self):
        cur = flat(generated("2026-11-22T00:00:00Z"))
        plan = copy.deepcopy(PLAN)
        plan["nodes"][0]["subtype"] = "api"
        with self.assertRaises(dp.PatchError):
            cf.shape_ops(cur, cf.prepare_target(plan, cur))

    def test_auto_layout_subflow_size(self):
        out = cf.auto_layout([{"id": "s", "kind": "subflow"}, {"id": "a", "parentId": "s"}, {"id": "b", "parentId": "s"}])
        sub = out[0]
        assert sub["width"] == 232 and sub["height"] == 60 + 132 * 2 - 24
        assert out[2]["y"] == 192


class DirectPatchAdditionsTests(unittest.TestCase):
    def snap(self):
        return {"name": "旧", "description": "", "nodes": [
            {"id": "start", "kind": "start", "title": "開始", "x": 0, "y": 0},
            {"id": "end", "kind": "end", "title": "終了", "x": 1, "y": 0}], "edges": []}

    def test_update_flow(self):
        plan = dp.plan_patch(self.snap(), [{"op": "update_flow", "patch": {"name": "新"}}])
        assert plan["expected"]["name"] == "新"
        assert dp.compare_to_expected(plan["expected"], self.snap()) == ["フローの name が計画と違う"]
        for bad in ({"name": ""}, {"title": "x"}, {}):
            with self.assertRaises(dp.PatchError):
                dp.plan_patch(self.snap(), [{"op": "update_flow", "patch": bad}])

    def test_update_flow_in_js(self):
        js = dp.js_apply("flow_x", [{"op": "update_flow", "patch": {"name": "新"}}], dp.HISTORY_LABEL)
        assert "st.op==='update_flow'" in js and "loadFlow" in js

    def test_subflow_size_only_on_subflow(self):
        ok = dp.validate_node({"id": "s", "kind": "subflow", "title": "t", "x": 0, "y": 0, "width": 232, "height": 300}, {})
        assert ok["width"] == 232
        with self.assertRaises(dp.PatchError):
            dp.validate_node({"id": "t", "kind": "tool", "title": "t", "x": 0, "y": 0, "width": 232}, {})


class EditLockTests(unittest.TestCase):
    def test_second_holder_is_refused_and_queue_skips(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.object(ff, "EDIT_LOCK_PATH", Path(d) / "f" / "edit.lock"):
            with ff.edit_lock(0, "create_flow") as a:
                assert a
                with ff.edit_lock(0, "other") as b:
                    assert not b
                assert ff.edit_lock_holder()["holder"] == "create_flow"
                sb = mock.Mock()
                assert ff.queue_once(sb, quiet_when_empty=True) == 0
                sb.table.assert_not_called()  # 待ち箱を拾わない（running にしない）
            with ff.edit_lock(0, "again") as c:
                assert c
            assert stat.S_IMODE(os.stat(ff.EDIT_LOCK_PATH).st_mode) == 0o600


if __name__ == "__main__":
    unittest.main()
