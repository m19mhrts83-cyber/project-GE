#!/usr/bin/env python3
"""FlowForge の新しいフローを1コマンドで作る（ラスカル用・2026-11-22 松野さん了承）。

AI は呼ばない「プログラム」。FlowForge の生成AIは FlowForge 自身が動かす（画面のボタンを押すだけ）。

なぜ画面操作か:
  データを直接作ると、サーバーが持ち主として登録せず 403 flow_owner_mismatch になる（2026-11-22 確認）。
  置き場（Chrome の既定プロフィール）のトップで「AIにフローを作ってもらう」を押した時だけ、
  持ち主の登録・クラウド保存・共有発行が通る。そこで「作るのは画面・整えるのは直接編集（#554）」に分ける。

一連（工程番号は 54b の「新規作成コマンド」と同じ）:
  1. 共通の編集ロックを取る（待ち箱の常駐・手元の編集と同じ。取れるまで待つ）／待ち箱が空になるまで待つ
  2. 置き場の FlowForge タブを1つに絞る（他のタブは元 URL を台帳に書いて about:blank へ。最後に戻す）
  3. 全フローの写し（Git 対象外・0600）
  4. トップに確定工程文を入れて「AIにフローを作ってもらう」を1回だけ押す。新しい flowId が1本だけ増えたか
  5. クラウド保存の確認（画面「クラウド同期済」＋画面と同じ sync API が 200）
  6. --plan があれば、確定の形との差分を出し、#554 の直接編集で整える（12操作ずつ・各回 verified 必須）
  7. 「フローを共有」で閲覧リンクを発行し、共有 API の中身と手元を照合
  8. 対象以外の全フローが写しと同じか
  9. すべて通った時だけ verified。登録（registry・共有リンク一覧・status_sync）の手順を出す（自動では書かない）

台帳（~/git-repos/.jarvis_state/flowforge/create_ledger.json・0600）:
  同じ工程文（前後の空白・改行の違いは同じとみなす）では二度作らない。途中で止まったら、同じコマンドで続きから。
  生成ボタンを押した後に止まった時は、押した時刻より後にできたフローを探して引き継ぐ。
  見つからない時は止まる（画面で作られていないと確かめてから --retry-generate）。

使い方:
  python scripts/jarvis_flowforge_create_flow.py --text-file 工程.txt --plan 確定.json --dry-run   # 何も変えない
  python scripts/jarvis_flowforge_create_flow.py --text-file 工程.txt --plan 確定.json --agent 318
  python scripts/jarvis_flowforge_create_flow.py --text-file 工程.txt --status                       # 台帳だけ見る

--plan（確定の形）: {"name", "description", "nodes": [...], "edges": [...]}
  nodes: id・kind（start/end/tool/claude/human/subflow）・title、任意で parentId・subtype・description・meta・toolName・x・y
  （x・y を省くと並び順で置く。サブフローは width・height も可）。edges: id・source・target。開始・終了は各1、各範囲は一本道。
  開始・終了の id は生成されたもの（start / end）に読み替える。flowId は生成されたものを使う（書かなくてよい）。

安全:
  - 生成ボタンは1回だけ。待ちきれなくても押し直さない（台帳に「押した」と残す）
  - 作ったフローは消さない。「みんなのフローに載せる」は押さない。持ち主でないブラウザで編集 URL を開かない
  - 匿名 ID・cookie・sync の本文は読まない／出さない（記録するのは HTTP 状態と ok だけ）
詳細: docs/AIエージェントチーム/54b_FlowForge読取プロキシ_OpenAPI_20261106.md「新規作成コマンド」
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
import jarvis_flowforge_assistant_paste as ff  # noqa: E402
import jarvis_flowforge_direct_patch as dp  # noqa: E402
import jarvis_flowforge_migrate_to_home as mg  # noqa: E402
import jarvis_flowforge_share_fetch as share  # noqa: E402

BASE = ff.BASE
STATE_DIR = Path(os.environ.get("FLOWFORGE_STATE_DIR") or Path.home() / "git-repos" / ".jarvis_state" / "flowforge")
LEDGER_PATH = STATE_DIR / "create_ledger.json"
BACKUP_DIR = REPO / ".jarvis_state" / "flowforge_backups"
MAX_TEXT = 2000
GENERATE_TIMEOUT_SEC = 300
LOCK_WAIT_SEC = 900
QUEUE_WAIT_SEC = 900
SHARE_CHECK_TRIES = 6

# 終了コード
EXIT_OK, EXIT_PREFLIGHT, EXIT_QUEUE, EXIT_LOCK, EXIT_GENERATE, EXIT_UNVERIFIED, EXIT_PLAN = 0, 2, 3, 4, 5, 11, 13


class CreateStop(Exception):
    """安全のために止めた。stage は止まった工程、code は終了コード。"""

    def __init__(self, code: int, stage: str, message: str):
        super().__init__(message)
        self.code, self.stage = code, stage
        self.flow_id: str | None = None
        self.share_url: str | None = None


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def parse_iso(s: str | None) -> float | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


# ---------- 台帳（純粋な部分） ----------

def normalize_text(text: str) -> str:
    lines = text.replace("\r\n", "\n").replace("\r", "\n").strip().split("\n")
    return "\n".join(line.rstrip() for line in lines)


def text_key(text: str) -> str:
    """同じ工程文かどうかの鍵（本文そのものは台帳に残さない）。"""
    return hashlib.sha256(normalize_text(text).encode("utf-8")).hexdigest()


def plan_key(plan: Any) -> str | None:
    if plan is None:
        return None
    return hashlib.sha256(json.dumps(plan, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


class Ledger:
    """重複作成防止と再開のための操作台帳（JSON・0600）。読めない時は「空」と扱わずに止める。"""

    def __init__(self, path: Path):
        self.path = path

    def load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"version": 1, "entries": {}}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception as e:
            raise CreateStop(EXIT_PREFLIGHT, "ledger", f"台帳を読めません（{self.path}: {type(e).__name__}）。直すまで作りません")
        if not isinstance(data, dict) or not isinstance(data.get("entries"), dict):
            raise CreateStop(EXIT_PREFLIGHT, "ledger", f"台帳の形が違います（{self.path}）。直すまで作りません")
        return data

    def get(self, key: str) -> dict[str, Any] | None:
        return self.load()["entries"].get(key)

    def put(self, key: str, entry: dict[str, Any]) -> None:
        data = self.load()
        entry["updated_at"] = now_iso()
        data["entries"][key] = entry
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        tmp = self.path.with_name(self.path.name + f".tmp{os.getpid()}")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(data, stream, ensure_ascii=False, indent=1)
        os.replace(tmp, self.path)
        os.chmod(self.path, 0o600)


def set_state(entry: dict[str, Any], state: str, **extra: Any) -> dict[str, Any]:
    entry["state"] = state
    entry.update(extra)
    entry.setdefault("history", []).append({"state": state, "at": now_iso()})
    return entry


# ---------- 確定の形（純粋な部分） ----------

STEP_X, TOP_Y, CHILD_X, CHILD_Y0, CHILD_STEP, SUB_W = 260, 176, 16, 60, 132, 232


def auto_layout(nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """x・y を省いたノードに、並び順で位置を付ける（上の段は横一列、サブフローの中は縦一列）。"""
    out = [dict(n) for n in nodes]
    top = [n for n in out if not n.get("parentId")]
    for i, n in enumerate(top):
        n.setdefault("x", STEP_X * i)
        n.setdefault("y", TOP_Y)
    for sub in (n for n in out if n.get("kind") == "subflow"):
        kids = [n for n in out if n.get("parentId") == sub["id"]]
        for k, n in enumerate(kids):
            n.setdefault("x", CHILD_X)
            n.setdefault("y", CHILD_Y0 + CHILD_STEP * k)
        sub.setdefault("width", SUB_W)
        sub.setdefault("height", CHILD_Y0 + CHILD_STEP * max(1, len(kids)) - 24)
    return out


def prepare_target(raw: Any, current: dict[str, Any]) -> dict[str, Any]:
    """確定の形を、生成されたフローに当てはめて点検する（PatchError なら何も変えない）。

    - 開始・終了は生成されたもの（ID・位置）を使う
    - 生成されたノードと同じ ID・同じ種別のノードは残す扱い（位置は生成のまま）
    """
    if not isinstance(raw, dict) or not isinstance(raw.get("nodes"), list) or not isinstance(raw.get("edges"), list):
        raise dp.PatchError("確定の形は name・nodes・edges を持つ JSON にしてください")
    cur = dp.node_map(current)
    cur_start = next((n for n in current["nodes"] if n.get("kind") == "start"), None)
    cur_end = next((n for n in current["nodes"] if n.get("kind") == "end"), None)
    if not cur_start or not cur_end:
        raise dp.PatchError("生成されたフローに開始・終了がありません")
    rename: dict[str, str] = {}
    for kind, node in (("start", cur_start), ("end", cur_end)):
        hits = [n for n in raw["nodes"] if isinstance(n, dict) and n.get("kind") == kind]
        if len(hits) != 1:
            raise dp.PatchError(f"確定の形には {kind} がちょうど1つ必要です")
        rename[str(hits[0].get("id"))] = node["id"]
    nodes = []
    for n in raw["nodes"]:
        if not isinstance(n, dict):
            raise dp.PatchError("node must be an object")
        m = {k: v for k, v in n.items() if v is not None}
        m["id"] = rename.get(str(m.get("id")), m.get("id"))
        if m.get("parentId"):
            m["parentId"] = rename.get(str(m["parentId"]), m["parentId"])
        old = cur.get(m["id"])
        if old and old.get("kind") == m.get("kind") and (old.get("parentId") or None) == (m.get("parentId") or None):
            m["x"], m["y"] = old.get("x"), old.get("y")
        nodes.append(m)
    edges = [
        {**e, "source": rename.get(str(e.get("source")), e.get("source")),
         "target": rename.get(str(e.get("target")), e.get("target"))}
        for e in raw["edges"] if isinstance(e, dict)
    ]
    if len(edges) != len(raw["edges"]):
        raise dp.PatchError("edge must be an object")
    flow = {"id": current["id"], "name": raw.get("name"), "description": raw.get("description", ""),
            "nodes": auto_layout(nodes), "edges": edges}
    return dp.validate_flow(flow)


FIELDS = ("parentId", "kind", "subtype", "title", "description", "meta", "toolName")


def flow_diffs(expected: dict[str, Any], actual: dict[str, Any]) -> list[str]:
    """意味のある違い（名前・説明・ノードの種別と本文・矢印）。位置は比べない。空なら同じ。"""
    out: list[str] = []
    for k in ("name", "description"):
        if (expected.get(k) or "") != (actual.get(k) or ""):
            out.append(f"フローの {k} が違う")
    a = mg.normalize(expected.get("nodes") or [], expected.get("edges") or [])
    b = mg.normalize(actual.get("nodes") or [], actual.get("edges") or [])
    an, bn = {n["id"]: n for n in a["nodes"]}, {n["id"]: n for n in b["nodes"]}
    for nid in sorted(an.keys() - bn.keys()):
        out.append(f"足りないノード: {an[nid]['title'] or nid}")
    for nid in sorted(bn.keys() - an.keys()):
        out.append(f"余分なノード: {bn[nid]['title'] or nid}")
    for nid in sorted(an.keys() & bn.keys()):
        for k in FIELDS:
            if an[nid][k] != bn[nid][k]:
                out.append(f"ノード「{an[nid]['title'] or nid}」の {k} が違う")
    for e in a["edges"]:
        if e not in b["edges"]:
            out.append(f"足りない矢印: {e[0]} → {e[1]}")
    for e in b["edges"]:
        if e not in a["edges"]:
            out.append(f"余分な矢印: {e[0]} → {e[1]}")
    return out


def shape_ops(current: dict[str, Any], target: dict[str, Any]) -> list[dict[str, Any]]:
    """生成されたフローを確定の形にする操作（#554 の直接編集の op）。

    順番: フロー名・説明 → 要らない矢印を外す → 要らないノードを消す（子から）→ ノードを足す（親から）
          → 残すノードの本文 → 矢印を足す（確定の順）
    """
    cur, tgt = dp.node_map(current), dp.node_map(target)

    def same_shape(a: dict[str, Any], b: dict[str, Any]) -> bool:
        return all((a.get(k) or None) == (b.get(k) or None) for k in ("kind", "subtype", "parentId"))

    keep = {i for i in cur.keys() & tgt.keys() if same_shape(cur[i], tgt[i])}
    for n in current["nodes"]:
        if n.get("kind") in {"start", "end"} and n["id"] not in keep:
            raise dp.PatchError(f"開始・終了（{n.get('title') or n['id']}）の種別は変えられません。確定の形の subtype を外してください")
    ops: list[dict[str, Any]] = []
    fpatch = {k: target.get(k) or "" for k in ("name", "description") if (current.get(k) or "") != (target.get(k) or "")}
    if fpatch:
        ops.append({"op": "update_flow", "patch": fpatch})
    want = {(e["source"], e["target"]) for e in target["edges"]}
    kept_pairs = set()
    for e in current["edges"]:
        pair = (e["source"], e["target"])
        if pair in want and e["source"] in keep and e["target"] in keep and pair not in kept_pairs:
            kept_pairs.add(pair)
        else:
            ops.append({"op": "remove_edge", "id": e["id"]})
    gone = [n for n in current["nodes"] if n["id"] not in keep]
    for n in sorted(gone, key=lambda n: 0 if n.get("parentId") else 1):
        ops.append({"op": "remove_node", "id": n["id"]})
    fresh = [n for n in target["nodes"] if n["id"] not in keep]
    for n in sorted(fresh, key=lambda n: 1 if n.get("parentId") else 0):
        node = {k: v for k, v in n.items() if v not in (None, "")}
        ops.append({"op": "add_node", "node": node})
    for nid in [n["id"] for n in target["nodes"] if n["id"] in keep]:
        patch = {k: tgt[nid].get(k) or "" for k in dp.PATCHABLE_KEYS if (cur[nid].get(k) or "") != (tgt[nid].get(k) or "")}
        if patch.get("title") == "":
            raise dp.PatchError("title を空にはできません")
        if patch:
            ops.append({"op": "update_node", "id": nid, "patch": patch})
    for e in target["edges"]:
        if (e["source"], e["target"]) not in kept_pairs:
            ops.append({"op": "add_edge", "source": e["source"], "target": e["target"]})
    return ops


def chunk_ops(ops: list[dict[str, Any]], size: int = dp.MAX_OPS) -> list[list[dict[str, Any]]]:
    return [ops[i:i + size] for i in range(0, len(ops), size)]


def simulate(current: dict[str, Any], chunks: list[list[dict[str, Any]]], target: dict[str, Any]) -> dict[str, Any]:
    """実際に触る前に、全部の回を計画だけで通す。最後が確定の形にならなければ PatchError。"""
    work = {k: current[k] for k in ("name", "description") if k in current}
    work.update({"nodes": [dict(n) for n in current["nodes"]], "edges": [dict(e) for e in current["edges"]]})
    for chunk in chunks:
        work = dp.plan_patch(work, chunk)["expected"]
    left = flow_diffs(target, work)
    if left:
        raise dp.PatchError("整形の計画が確定の形になりません（作りの不具合）: " + " / ".join(left[:5]))
    return work


def registry_steps(agent: str | None, fid: str, share_url: str | None) -> list[str]:
    """登録は自動では書かない。既存の方式（registry・共有リンク一覧・status_sync）の手順だけ出す。"""
    a = agent or "<社員番号>"
    return [
        "worktree で作業する（~/git-repos の本体では登録しない）",
        f"docs/AIエージェントチーム/agents_registry.yaml の '{a}' 行に flowforge_id: {fid} と flowforge_url: {BASE}/flows/{fid}",
        f"config/flowforge_share_urls.json の by_agent_id['{a}'] と by_flow_id['{fid}'] に {share_url or '<共有URL>'}",
        "python scripts/jarvis_agent_team_status_sync.py --no-drive で agentTeam.json を作り直す（他の部門ボードの日付の書き換えは戻す）",
        "意図したファイルだけを PR にする（本人の了承の後）",
    ]


# ---------- Chrome（テストでは差し替える） ----------

JS_TOP_STATE = r"""
(function(){
  var tas=[].slice.call(document.querySelectorAll('textarea')).filter(function(t){return (t.placeholder||'').indexOf('AI Assistant')<0;});
  var b=[].slice.call(document.querySelectorAll('button')).filter(function(b){return (b.innerText||'').indexOf('AIにフローを作ってもらう')>=0;});
  return JSON.stringify({path:location.pathname,textareas:tas.length,button:b.length,disabled:b.length?!!b[0].disabled:null,
    value:tas.length===1?tas[0].value.length:null});
})()
"""

JS_TOP_FILL = r"""
(function(){
  var tas=[].slice.call(document.querySelectorAll('textarea')).filter(function(t){return (t.placeholder||'').indexOf('AI Assistant')<0;});
  if(tas.length!==1) return 'textareas:'+tas.length;
  var set=Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype,'value').set;
  set.call(tas[0],%(text)s); tas[0].dispatchEvent(new Event('input',{bubbles:true}));
  return 'filled:'+tas[0].value.length;
})()
"""

JS_TOP_CLICK = r"""
(function(){
  var b=[].slice.call(document.querySelectorAll('button')).filter(function(b){return (b.innerText||'').indexOf('AIにフローを作ってもらう')>=0;});
  if(b.length!==1) return 'buttons:'+b.length; if(b[0].disabled) return 'disabled'; b[0].click(); return 'clicked';
})()
"""

JS_SKIP_OVERLAY = r"""
(function(){
  var b=[].slice.call(document.querySelectorAll('button')).filter(function(b){return (b.innerText||'').trim()==='スキップ';})[0];
  if(!b) return 'none'; b.click(); return 'skipped';
})()
"""

JS_ALL_FLOWS = r"""
(function(){try{var raw=JSON.parse(localStorage.getItem('flowforge:flows')||'null');
  if(!raw||!raw.state||!raw.state.flows) return JSON.stringify({ok:false,error:'no_flows'});
  return JSON.stringify({ok:true,flows:raw.state.flows});}catch(e){return JSON.stringify({ok:false,error:'unreadable'});}})()
"""

# 画面が自分で送る sync の結果だけを覚える（ページ本体の世界）。要求の中身・匿名 ID・cookie は見ない
JS_OBSERVE = (
    "(function(){if(window.__jarvisFfNet)return 'observer_ready';window.__jarvisFfNet=[];var old=window.fetch;"
    "window.fetch=async function(){var a=arguments;var u=String((a[0]&&a[0].url)||a[0]);var r=await old.apply(this,a);"
    "if(u.indexOf('/api/flows/sync')>=0){var e={status:r.status,at:new Date().toISOString()};window.__jarvisFfNet.push(e);"
    "r.clone().json().then(function(b){e.ok=!!(b&&b.ok===true);var x=b&&(b.error||b.detail);e.error=x?String(x).slice(0,60):null;})"
    ".catch(function(){});}return r;};return 'observer_ready';})()"
)
JS_OBSERVED = "JSON.stringify(window.__jarvisFfNet||null)"


class Chrome:
    """本人の Chrome（AppleScript）。タブは (window id, tab id) の永続 ID で指す。"""

    def tabs(self) -> list[tuple[int, int]]:
        return ff.find_tabs(BASE)

    def url(self, tab: tuple[int, int]) -> str:
        return ff.osa(f'tell application "Google Chrome" to return URL of tab id {tab[1]} of window id {tab[0]}')

    def js(self, tab: tuple[int, int], code: str) -> str:
        return ff.run_js(*tab, code)

    def main(self, tab: tuple[int, int], code: str) -> str:
        return ff.run_main(*tab, code)

    def set_url(self, tab: tuple[int, int], url: str) -> None:
        ff.osa(f'tell application "Google Chrome" to set URL of tab id {tab[1]} of window id {tab[0]} to {ff.as_str(url)}')

    def reload(self, tab: tuple[int, int]) -> None:
        ff.osa(f'tell application "Google Chrome" to reload tab id {tab[1]} of window id {tab[0]}')

    def new_tab(self, win: int, url: str) -> tuple[int, int]:
        """そのウィンドウ（＝置き場のプロフィール）に背景で開く。前に見ていたタブは前に出したまま。"""
        new_id = ff.osa(
            f'tell application "Google Chrome" to tell window id {win}\n'
            "set previousActive to active tab index\n"
            f"set fresh to make new tab with properties {{URL:{ff.as_str(url)}}}\n"
            "set freshId to id of fresh\n"
            "set active tab index to previousActive\n"
            "return freshId\nend tell"
        )
        return (win, int(new_id))

    def open_home(self, url: str) -> None:
        ff.open_in_home_profile(url)

    def sleep(self, sec: float) -> None:
        time.sleep(sec)


class Services:
    """Chrome 以外の外の道具（待ち箱・ロック・#554 の直接編集・共有 API）。テストでは差し替える。"""

    def lock(self, wait: float):
        return ff.edit_lock(wait, "create_flow")

    def lock_holder(self) -> dict[str, Any]:
        return ff.edit_lock_holder()

    def queue_active(self) -> list[dict[str, Any]]:
        sb = ff.queue_client()
        return (sb.table(ff.QUEUE_TABLE).select("id,status").in_("status", ["queued", "running"]).execute().data or [])

    def freshness(self, tab: tuple[int, int]) -> list[str]:
        return ff.tab_freshness(tab)

    def read_store(self, tab: tuple[int, int], fid: str) -> dict[str, Any]:
        return ff.read_store(tab, fid)

    def sync(self, tab: tuple[int, int], fid: str) -> dict[str, Any]:
        return ff.sync_owned(tab, fid)

    def direct_patch(self, fid: str, ops: list[dict[str, Any]], tab: tuple[int, int]) -> dict[str, Any]:
        return ff.direct_patch(fid, ops, tab=tab)

    def fetch_share(self, share_id: str) -> dict[str, Any]:
        return share.fetch_share(BASE, share_id, 25.0)


# ---------- 本体 ----------

class Creator:
    def __init__(self, chrome: Chrome, svc: Services, ledger: Ledger, backup_dir: Path = BACKUP_DIR,
                 generate_timeout: float = GENERATE_TIMEOUT_SEC, queue_wait: float = QUEUE_WAIT_SEC,
                 lock_wait: float = LOCK_WAIT_SEC):
        self.c, self.s, self.ledger, self.backup_dir = chrome, svc, ledger, backup_dir
        self.generate_timeout, self.queue_wait, self.lock_wait = generate_timeout, queue_wait, lock_wait
        self.log: list[str] = []

    def say(self, msg: str) -> None:
        self.log.append(msg)
        print(msg, file=sys.stderr, flush=True)

    # --- 1. 待ち箱 ---
    def wait_queue_idle(self, stage: str) -> None:
        deadline = time.time() + self.queue_wait
        while True:
            try:
                rows = self.s.queue_active()
            except BaseException as e:  # 資格情報が無い（SystemExit）も含む。読めない＝空とは扱わない
                raise CreateStop(EXIT_QUEUE, stage, f"待ち箱を読めません（{type(e).__name__}）。空と確かめられないので止めます")
            if not rows:
                return
            if time.time() >= deadline:
                raise CreateStop(EXIT_QUEUE, stage, f"待ち箱に処理中・待ちが {len(rows)} 件あり、空になりませんでした")
            self.say(f"待ち箱に {len(rows)} 件あるので待ちます（{stage}）")
            self.c.sleep(10)

    # --- 2. タブ ---
    def flows_in(self, tab: tuple[int, int]) -> dict[str, Any] | None:
        try:
            got = json.loads(self.c.js(tab, JS_ALL_FLOWS))
        except Exception:
            return None
        return got.get("flows") if got.get("ok") else None

    def home_tabs(self) -> list[tuple[int, int]]:
        return [t for t in self.c.tabs() if self.flows_in(t) is not None]

    def wait_readable(self, tab: tuple[int, int], sec: float = 20) -> dict[str, Any]:
        deadline = time.time() + sec
        while True:
            flows = self.flows_in(tab)
            if flows is not None:
                return flows
            if time.time() >= deadline:
                raise CreateStop(EXIT_PREFLIGHT, "tab", "置き場のタブの保存内容を読めません（読み込みが終わらない）")
            self.c.sleep(1.5)

    def prepare_tab(self, entry: dict[str, Any], key: str) -> tuple[int, int]:
        """置き場の FlowForge タブを1つに絞る。他は元 URL を台帳に書いてから about:blank。"""
        home = self.home_tabs()
        if not home:
            self.c.open_home(BASE + "/")
            self.c.sleep(6)
            home = self.home_tabs()
        if not home:
            raise CreateStop(EXIT_PREFLIGHT, "tab", "置き場の Chrome で FlowForge を読めません（「Apple Events からの JavaScript を許可」を確かめる）")
        fid = entry.get("flow_id")
        if fid and fid not in (self.flows_in(home[0]) or {}):
            raise CreateStop(EXIT_PREFLIGHT, "tab", f"台帳のフロー {fid} が置き場にありません。編集画面は開かずに止めます")
        urls = {t: self.c.url(t) for t in home}
        work = None
        if fid:
            work = next((t for t in home if f"/flows/{fid}" in urls[t]), None)
        if work is None and not fid:
            work = next((t for t in home if urls[t].split("?")[0].rstrip("/") == BASE), None)
        parked = [{"win": t[0], "tab": t[1], "url": urls[t]} for t in home if t != work]
        entry["parked_tabs"] = (entry.get("parked_tabs") or []) + parked
        self.ledger.put(key, entry)  # 戻す先を先に書く（途中で落ちても手で戻せる）
        for p in parked:
            self.c.set_url((p["win"], p["tab"]), "about:blank")
        if parked:
            self.say(f"他の FlowForge タブ {len(parked)} 枚を about:blank にしました（最後に戻します）")
        if work is None:
            work = self.c.new_tab(home[0][0], f"{BASE}/flows/{fid}" if fid else BASE + "/")
            self.c.sleep(5)
        else:
            self.c.reload(work)
            self.c.sleep(5)
        self.wait_readable(work)
        return work

    def restore_tabs(self, entry: dict[str, Any]) -> list[dict[str, Any]]:
        out = []
        for p in entry.get("parked_tabs") or []:
            try:
                self.c.set_url((p["win"], p["tab"]), p["url"])
                out.append({"tab": p["tab"], "restored": True})
            except Exception:
                out.append({"tab": p["tab"], "restored": False, "url": p["url"]})
        entry["parked_tabs"] = [p for p, r in zip(entry.get("parked_tabs") or [], out) if not r["restored"]]
        return out

    def check_fresh(self, tab: tuple[int, int], stage: str) -> str:
        try:
            reasons = self.s.freshness(tab)
        except ff.PasteStop as e:
            # トップページには保存部品が無いことがある。読み込み直した直後で他のタブも止めてあるので続ける
            if "store_not_found" in str(e) and "/flows/" not in self.c.url(tab):
                return "top_page_no_store"
            raise CreateStop(EXIT_PREFLIGHT, stage, str(e))
        if reasons:
            raise CreateStop(EXIT_PREFLIGHT, stage, "タブの内容が保存内容と食い違っています: " + " / ".join(reasons[:3]))
        return "fresh"

    # --- 3. 写し ---
    def backup(self, tab: tuple[int, int], label: str) -> tuple[Path, dict[str, Any]]:
        flows = self.wait_readable(tab)
        self.backup_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        path = self.backup_dir / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S") + "_create_" + uuid.uuid4().hex[:12] + ".json")
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump({"label": label, "flows": flows}, stream, ensure_ascii=False)
        return path, flows

    # --- 4. 生成 ---
    def new_flow_ids(self, flows: dict[str, Any], known: list[str], since: float | None) -> list[str]:
        out = []
        for fid, f in flows.items():
            if fid in known:
                continue
            created = parse_iso((f or {}).get("createdAt"))
            if since is not None and created is not None and created < since - 5:
                continue
            out.append(fid)
        return sorted(out)

    def generate(self, tab: tuple[int, int], text: str, entry: dict[str, Any], key: str, before: dict[str, Any]) -> str:
        url = self.c.url(tab)
        if url.split("?")[0].rstrip("/") != BASE:
            self.c.set_url(tab, BASE + "/")
            self.c.sleep(5)
            before = self.wait_readable(tab)
        state = json.loads(self.c.js(tab, JS_TOP_STATE))
        if state.get("textareas") != 1 or state.get("button") != 1:
            raise CreateStop(EXIT_PREFLIGHT, "generate", f"トップの入力欄か生成ボタンが見つかりません（画面の作りが変わった可能性）: {state}")
        self.wait_queue_idle("generate")
        self.check_fresh(tab, "generate")
        self.c.main(tab, JS_OBSERVE)
        res = self.c.js(tab, JS_TOP_FILL % {"text": json.dumps(text, ensure_ascii=False)})
        if not res.startswith("filled:"):
            raise CreateStop(EXIT_PREFLIGHT, "generate", f"入力できませんでした（{res}）")
        self.c.sleep(0.8)
        state = json.loads(self.c.js(tab, JS_TOP_STATE))
        if state.get("disabled"):
            raise CreateStop(EXIT_PREFLIGHT, "generate", "生成ボタンが押せない状態です（入力が反映されていない）")
        known = sorted(before)
        set_state(entry, "generate_clicked", known_ids=known, clicked_at=now_iso())
        self.ledger.put(key, entry)  # 押す前に「押す」と書く。落ちても二度押さない
        res = self.c.js(tab, JS_TOP_CLICK)
        if res != "clicked":
            set_state(entry, "generate_not_clicked")
            self.ledger.put(key, entry)
            raise CreateStop(EXIT_PREFLIGHT, "generate", f"生成ボタンを押せませんでした（{res}）")
        self.say("「AIにフローを作ってもらう」を1回押しました。生成を待ちます")
        return self.wait_new_flow(tab, entry, key)

    def wait_new_flow(self, tab: tuple[int, int], entry: dict[str, Any], key: str) -> str:
        deadline = time.time() + self.generate_timeout
        since = parse_iso(entry.get("clicked_at"))
        seen: list[str] = []
        while True:
            flows = self.flows_in(tab) or {}
            new = self.new_flow_ids(flows, entry.get("known_ids") or [], since)
            if new and new == seen:  # 2回続けて同じなら落ち着いた
                if len(new) != 1:
                    raise CreateStop(EXIT_GENERATE, "generate", f"新しいフローが {len(new)} 本できました（{', '.join(new)}）。消さずに止めます")
                set_state(entry, "created", flow_id=new[0])
                self.ledger.put(key, entry)
                return new[0]
            seen = new
            if time.time() >= deadline:
                raise CreateStop(EXIT_GENERATE, "generate",
                                 "生成が時間内に終わりませんでした。押し直しはしません。同じコマンドで続きから確かめます")
            self.c.sleep(3)

    def adopt_after_click(self, tab: tuple[int, int], entry: dict[str, Any], key: str, retry: bool) -> str | None:
        """前回「押した」まで進んで止まった時。押した後にできたフローがあれば引き継ぐ。"""
        flows = self.flows_in(tab) or {}
        new = self.new_flow_ids(flows, entry.get("known_ids") or [], parse_iso(entry.get("clicked_at")))
        if len(new) == 1:
            set_state(entry, "created", flow_id=new[0], adopted=True)
            self.ledger.put(key, entry)
            return new[0]
        if len(new) > 1:
            raise CreateStop(EXIT_GENERATE, "generate", f"押した後にできたフローが {len(new)} 本あります（{', '.join(new)}）。どれか決められないので止めます")
        if not retry:
            raise CreateStop(EXIT_GENERATE, "generate",
                             "前回、生成ボタンを押した記録がありますが、新しいフローが見つかりません。"
                             "画面で作られていないことを確かめてから --retry-generate を付けてください")
        return None

    def open_editor(self, tab: tuple[int, int], fid: str) -> None:
        for _ in range(10):
            if f"/flows/{fid}" in self.c.url(tab):
                break
            self.c.sleep(2)
        else:
            self.c.set_url(tab, f"{BASE}/flows/{fid}")  # もう持ち主のフローなので開いてよい
            self.c.sleep(5)
        self.wait_readable(tab)
        self.c.js(tab, JS_SKIP_OVERLAY)

    # --- 5. クラウド保存 ---
    def confirm_sync(self, tab: tuple[int, int], fid: str) -> dict[str, Any]:
        ui = ""
        for _ in range(20):
            ui = self.c.js(tab, ff.JS_SYNC_TEXT)
            if "同期済" in ui or "同期失敗" in ui:
                break
            self.c.sleep(1.5)
        try:
            observed = json.loads(self.c.main(tab, JS_OBSERVED) or "null")
        except Exception:
            observed = None
        bad = [o for o in observed or [] if o.get("status") == 403 or "owner" in str(o.get("error") or "")]
        out: dict[str, Any] = {"ui": ui, "observed": observed}
        if bad or "同期失敗" in ui:
            out["ok"] = False
            return out
        try:
            cloud = self.s.sync(tab, fid)
        except (dp.PatchError, ff.PasteStop) as e:
            cloud = {"ok": False, "detail": str(e)[:120]}
        out["api"] = {"ok": bool(cloud.get("ok")), "status": cloud.get("status"), "detail": cloud.get("detail")}
        out["ok"] = bool(cloud.get("ok")) and "同期済" in ui
        return out

    # --- 7. 共有 ---
    def issue_share(self, tab: tuple[int, int]) -> str:
        self.c.js(tab, JS_SKIP_OVERLAY)
        res = self.c.js(tab, mg.JS_CLICK_SHARE)
        if res != "clicked":
            raise CreateStop(EXIT_UNVERIFIED, "share", f"「フローを共有」を押せませんでした（{res}）")
        url = ""
        for _ in range(15):
            self.c.sleep(1.5)
            url = self.c.js(tab, mg.JS_READ_SHARE)
            if "/share/" in url:
                break
        self.c.js(tab, mg.JS_CLOSE_DIALOG)
        if "/share/" not in url:
            raise CreateStop(EXIT_UNVERIFIED, "share", "共有 URL を読めませんでした")
        return url.strip()

    def check_share(self, share_url: str, fid: str, local: dict[str, Any]) -> dict[str, Any]:
        sid = share.share_id_from_url(share_url)
        diffs: list[str] = ["未取得"]
        for i in range(SHARE_CHECK_TRIES):
            try:
                flow = (self.s.fetch_share(sid) or {}).get("flow") or {}
            except BaseException as e:
                flow, diffs = {}, [f"共有 API を読めません（{type(e).__name__}）"]
            if flow:
                diffs = ([f"共有リンクが別のフロー（{flow.get('id')}）を指しています"] if flow.get("id") != fid
                         else flow_diffs(local, flow))
                if not diffs:
                    return {"ok": True, "tries": i + 1}
            if i + 1 < SHARE_CHECK_TRIES:
                self.c.sleep(3)
        return {"ok": False, "diffs": diffs[:20]}

    # --- 8. 他のフロー ---
    def other_changes(self, tab: tuple[int, int], before: dict[str, Any], fid: str) -> list[str]:
        after = self.wait_readable(tab)
        return sorted(k for k in before.keys() | after.keys() if k != fid and before.get(k) != after.get(k))

    # --- 全体 ---
    def run(self, text: str, plan: Any, agent: str | None = None, retry_generate: bool = False) -> dict[str, Any]:
        text = normalize_text(text)
        if not text:
            raise CreateStop(EXIT_PREFLIGHT, "input", "工程文が空です")
        if len(text) > MAX_TEXT:
            raise CreateStop(EXIT_PREFLIGHT, "input", f"工程文が長すぎます（{len(text)} 文字。{MAX_TEXT} 文字まで）")
        key, pkey = text_key(text), plan_key(plan)
        entry = self.ledger.get(key)
        if entry and entry.get("state") == "verified" and entry.get("plan_sha") == pkey:
            return {**(entry.get("result") or {}), "already_done": True,
                    "note": "同じ工程文・同じ確定の形で作成済みです。作り直していません"}
        entry = entry or {"run_id": uuid.uuid4().hex[:12], "text_sha": key, "text_len": len(text), "created_at": now_iso()}
        if not entry.get("state"):
            set_state(entry, "started")
        entry["plan_sha"] = pkey
        self.ledger.put(key, entry)
        with self.s.lock(self.lock_wait) as got:
            if not got:
                raise CreateStop(EXIT_LOCK, "lock", f"編集ロックが取れません（{self.s.lock_holder().get('holder')} が使用中）")
            self.wait_queue_idle("start")
            try:
                result = self._run_locked(text, plan, agent, retry_generate, key, entry)
                entry.pop("last_stop", None)
                return result
            except (CreateStop, dp.PatchError, ff.PasteStop) as e:
                stop = e if isinstance(e, CreateStop) else (
                    CreateStop(EXIT_PLAN, "plan", "確定の形の点検で止めました（整形は未実行）: " + str(e))
                    if isinstance(e, dp.PatchError) else CreateStop(EXIT_UNVERIFIED, "browser", str(e)))
                # 状態（どこまで進んだか）は変えない。次は同じコマンドで続きから
                entry["last_stop"] = {"stage": stop.stage, "code": stop.code, "message": str(stop)[:300], "at": now_iso()}
                stop.flow_id, stop.share_url = entry.get("flow_id"), entry.get("share_url")
                raise stop from (None if stop is e else e)
            finally:
                entry["restored_tabs"] = self.restore_tabs(entry)
                self.ledger.put(key, entry)

    def _run_locked(self, text: str, plan: Any, agent: str | None, retry: bool, key: str,
                    entry: dict[str, Any]) -> dict[str, Any]:
        tab = self.prepare_tab(entry, key)
        backup_path, before = self.backup(tab, f"before create-flow {entry['run_id']}")
        out: dict[str, Any] = {"run_id": entry["run_id"], "backup_path": str(backup_path), "tab": list(tab)}
        fid = entry.get("flow_id")
        if not fid and entry.get("state") == "generate_clicked":
            fid = self.adopt_after_click(tab, entry, key, retry)
        if not fid:
            fid = self.generate(tab, text, entry, key, before)
        out["flow_id"], out["edit_url"] = fid, f"{BASE}/flows/{fid}"
        self.open_editor(tab, fid)

        sync = self.confirm_sync(tab, fid)
        out["sync"] = sync
        if not sync.get("ok"):
            raise CreateStop(EXIT_UNVERIFIED, "sync", "クラウド保存を確かめられませんでした（フローは消していません）: "
                             + json.dumps({k: sync.get(k) for k in ("ui", "api")}, ensure_ascii=False))
        if entry.get("state") in {"started", "created", "generate_clicked"}:
            set_state(entry, "synced")
            self.ledger.put(key, entry)

        current = self.s.read_store(tab, fid)
        out["generated"] = {"name": current.get("name"), "nodes": len(current["nodes"]), "edges": len(current["edges"])}
        target = None
        if plan is not None:
            target = prepare_target(plan, current)
            out["diffs_before"] = flow_diffs(target, current)
            ops = shape_ops(current, target)
            chunks = chunk_ops(ops)
            if ops:
                simulate(current, chunks, target)
            out["shape"] = {"ops": len(ops), "batches": []}
            for i, chunk in enumerate(chunks, 1):
                self.wait_queue_idle(f"shape {i}/{len(chunks)}")
                res = self.s.direct_patch(fid, chunk, tab)
                out["shape"]["batches"].append({k: res.get(k) for k in ("verified", "steps", "rolled_back", "cloud_sync")})
                if not res.get("verified"):
                    raise CreateStop(EXIT_UNVERIFIED, "shape", f"整形の {i}/{len(chunks)} 回目が計画どおりになりませんでした"
                                     f"（rolled_back={res.get('rolled_back')}）: " + " / ".join((res.get("unexpected") or [])[:5]))
            set_state(entry, "shaped")
            self.ledger.put(key, entry)
        after = self.s.read_store(tab, fid)
        out["nodes"], out["edges"] = len(after["nodes"]), len(after["edges"])
        out["name"] = after.get("name")
        out["diffs_after"] = flow_diffs(target, after) if target else None

        share_url = entry.get("share_url") or self.issue_share(tab)
        if not entry.get("share_url"):
            set_state(entry, "shared", share_url=share_url)
            self.ledger.put(key, entry)
        out["share_url"] = share_url
        out["share_check"] = self.check_share(share_url, fid, after)
        out["other_flows_changed"] = self.other_changes(tab, before, fid)
        out["verified"] = bool(sync.get("ok") and not out["diffs_after"] and out["share_check"].get("ok")
                               and not out["other_flows_changed"])
        if plan is None:
            out["note"] = "確定の形（--plan）が無いので、生成されたままです。整えてから使う"
        out["next_steps"] = registry_steps(agent, fid, share_url)
        set_state(entry, "verified" if out["verified"] else "unverified", result={
            k: out.get(k) for k in ("run_id", "flow_id", "edit_url", "share_url", "name", "nodes", "edges", "verified")})
        self.ledger.put(key, entry)
        return out


def dry_run(text: str, plan: Any, ledger: Ledger, chrome: Chrome, svc: Services) -> dict[str, Any]:
    """何も変えずに、入力・確定の形・台帳・ロック・待ち箱・タブを確かめる。"""
    text = normalize_text(text)
    out: dict[str, Any] = {"dry_run": True, "text_len": len(text), "text_ok": 0 < len(text) <= MAX_TEXT}
    entry = ledger.get(text_key(text))
    out["ledger"] = {k: (entry or {}).get(k) for k in ("state", "flow_id", "share_url", "run_id")} if entry else None
    if plan is not None:
        placeholder = {"id": "flow_placeholder00", "name": "", "description": "",
                       "nodes": [{"id": "start", "kind": "start", "title": "開始", "x": 0, "y": 0},
                                 {"id": "end", "kind": "end", "title": "終了", "x": 0, "y": 0}], "edges": []}
        try:
            t = prepare_target(plan, placeholder)
            out["plan"] = {"ok": True, "nodes": len(t["nodes"]), "edges": len(t["edges"]), "name": t["name"]}
        except dp.PatchError as e:
            out["plan"] = {"ok": False, "error": str(e)}
    with svc.lock(0) as got:
        out["lock_free"] = got
        if not got:
            out["lock_holder"] = svc.lock_holder().get("holder")
    try:
        out["queue_active"] = len(svc.queue_active())
    except BaseException as e:
        out["queue_active"] = f"読めません（{type(e).__name__}）"
    c = Creator(chrome, svc, ledger)
    home = c.home_tabs()
    fid = (entry or {}).get("flow_id")

    def kept(t: tuple[int, int]) -> bool:  # prepare_tab と同じ選び方（続きなら対象フローの画面、新規ならトップ）
        u = chrome.url(t)
        return f"/flows/{fid}" in u if fid else u.split("?")[0].rstrip("/") == BASE
    keep = next((t for t in home if kept(t)), None)
    out["home_tabs"] = len(home)
    out["tabs_to_park"] = len([t for t in home if t != keep])
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="FlowForge の新しいフローを画面操作で作り、確定の形に整えて照合する")
    ap.add_argument("--text-file", required=True, help="確定した工程文（UTF-8・2000文字まで）。トップの入力欄に入れる")
    ap.add_argument("--plan", help="確定の形（JSON）。あれば生成後に直接編集で整える")
    ap.add_argument("--agent", help="登録する社員番号（手順の表示だけ。登録は自動で書かない）")
    ap.add_argument("--dry-run", action="store_true", help="何も変えずに確かめる")
    ap.add_argument("--status", action="store_true", help="この工程文の台帳だけを表示")
    ap.add_argument("--retry-generate", action="store_true", help="前回押した生成が作られていないと確かめた時だけ、もう一度押す")
    ap.add_argument("--generate-timeout", type=float, default=GENERATE_TIMEOUT_SEC)
    args = ap.parse_args(argv)

    text = Path(args.text_file).read_text(encoding="utf-8")
    plan = json.loads(Path(args.plan).read_text(encoding="utf-8")) if args.plan else None
    ledger = Ledger(LEDGER_PATH)
    try:
        if args.status:
            print(json.dumps(ledger.get(text_key(text)), ensure_ascii=False, indent=1))
            return EXIT_OK
        if args.dry_run:
            print(json.dumps(dry_run(text, plan, ledger, Chrome(), Services()), ensure_ascii=False, indent=1))
            return EXIT_OK
        result = Creator(Chrome(), Services(), ledger, generate_timeout=args.generate_timeout).run(
            text, plan, args.agent, args.retry_generate)
    except CreateStop as e:
        print(json.dumps({"verified": False, "stopped_at": e.stage, "reason": str(e), "flow_id": e.flow_id,
                          "share_url": e.share_url, "resume": "原因を直して同じコマンドを実行すると続きから"},
                         ensure_ascii=False, indent=1))
        return e.code
    except dp.PatchError as e:
        print(json.dumps({"verified": False, "stopped_at": "plan", "reason": "確定の形の点検で止めました（整形は未実行）: " + str(e)},
                         ensure_ascii=False, indent=1))
        return EXIT_PLAN
    print(json.dumps(result, ensure_ascii=False, indent=1))
    return EXIT_OK if result.get("verified") or result.get("already_done") else EXIT_UNVERIFIED


if __name__ == "__main__":
    sys.exit(main())
