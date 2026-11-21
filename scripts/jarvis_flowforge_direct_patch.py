#!/usr/bin/env python3
"""FlowForge の直接編集（AIアシスタントを通さない）の部品（2026-11-21）。

なぜ要るか（311 で確認した事実。FlowForge の画面のプログラムを読んで原因を特定）:
  1. AIアシスタントの返事のあと、FlowForge は必ず「孤立ノードの修復」を走らせる
     （/api/flows/repair → だめなら機械的に接続）。変更されたノードに孤立があると、
     説明文だけの更新でも矢印が足される。
  2. AIアシスタントの返事のあと、必ず enforceSingleInOut（各ノードの矢印は入り1本・出1本）と
     自動整列が走る。
  3. 矢印の追加（addEdge）自体が、同じ始点／同じ終点の既存の矢印を外してから足す作り。
     → 合流・分岐は FlowForge のデータの形として持てない（AI の気まぐれではなく仕様）。
  どれも自然言語の指示では止められない。

対策: 画面が使っている保存部品（zustand の store）の操作を、ノード ID・矢印 ID を指定して直接呼ぶ。
  - AIアシスタントを通らないので、修復・強制・整列は走らない
  - 手で編集した時と同じ経路なので、履歴（元に戻す）とクラウド同期はそのまま働く
  - 事前に「この操作で何が変わるはずか」を計算し、実行後に一致を確かめる。違えば1手戻す

このファイルは、ブラウザに触らない純粋な計算（計画・検証）と、ページへ入れる JS の文字列だけを持つ。
ブラウザ操作は jarvis_flowforge_assistant_paste.py 側。
"""
from __future__ import annotations

import json
from typing import Any

# 直接編集で書き換えてよいノードの項目（種別や位置は変えない）
PATCHABLE_KEYS = ("title", "description", "meta", "toolName")
MAX_OPS = 12
# 直接編集が履歴に残す名前。自動で戻す時は、いちばん上の履歴がこの名前であることを確かめてから戻す
HISTORY_LABEL = "Jarvis 直接編集"
MAX_TEXT = 2000


class PatchError(Exception):
    """計画の段階で分かった問題（何も適用していない）。"""


# ---------- フローの読み方 ----------

def node_map(snap: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {n["id"]: n for n in snap.get("nodes", [])}


def subflow_of(nodes: dict[str, dict[str, Any]], node_id: str) -> str | None:
    """ノードが属するサブフローの ID（FlowForge の addEdge と同じ判定）。"""
    n = nodes.get(node_id)
    if not n or not n.get("parentId"):
        return None
    parent = nodes.get(n["parentId"])
    return parent["id"] if parent and parent.get("kind") == "subflow" else None


def lifted(nodes: dict[str, dict[str, Any]], source: str, target: str) -> tuple[str, str, bool]:
    """矢印の実際の始点・終点。サブフローをまたぐ矢印は、サブフローそのものに付け替わる。

    戻り値: (始点, 終点, 同じサブフローの中の矢印か)
    """
    o, s = subflow_of(nodes, source), subflow_of(nodes, target)
    inner = o is not None and o == s
    if inner:
        return source, target, True
    return o or source, s or target, False


def edge_conflicts(snap: dict[str, Any], source: str, target: str) -> list[dict[str, Any]]:
    """この矢印を足すと FlowForge が外す既存の矢印（入り1本・出1本の決まり）。"""
    nodes = node_map(snap)
    u, f, inner = lifted(nodes, source, target)
    out = []
    for e in snap.get("edges", []):
        eu, ef, e_inner = lifted(nodes, e["source"], e["target"])
        if inner:
            if e_inner and (e["source"] == u or e["target"] == f):
                out.append(e)
        else:
            if e_inner:
                continue
            if eu == u or ef == f:
                out.append(e)
    return out


def title_of(snap: dict[str, Any], node_id: str) -> str:
    n = node_map(snap).get(node_id)
    return (n or {}).get("title") or node_id


def edge_label(snap: dict[str, Any], e: dict[str, Any]) -> str:
    return f"{title_of(snap, e['source'])} → {title_of(snap, e['target'])}"


# ---------- 計画 ----------

def validate_node(raw: Any, existing: dict[str, Any]) -> dict[str, Any]:
    """Stable IDs and explicit positions; never infer an assignee or connect arrows."""
    import math
    import re
    if not isinstance(raw, dict):
        raise PatchError("node must be an object")
    n = dict(raw)
    allowed = {"id", "parentId", "kind", "subtype", "x", "y", *PATCHABLE_KEYS}
    if set(n) - allowed:
        raise PatchError("unknown node fields")
    if not isinstance(n.get("id"), str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", n["id"]):
        raise PatchError("invalid node id")
    if n["id"] in existing:
        raise PatchError("node id already exists")
    if n.get("kind") not in {"start", "end", "tool", "claude", "human", "subflow"}:
        raise PatchError("invalid node kind")
    if n["kind"] in {"start","end"} and any(v.get("kind")==n["kind"] for v in existing.values()):
        raise PatchError("start/end already exists")
    if n.get("subtype") and n["subtype"] not in {"think","web","folder","code","mcp","connector","api","cli","browser","desktop","notify","human"}:
        raise PatchError("invalid subtype")
    for k in ("title", "description", "meta", "toolName", "subtype"):
        if k in n and (not isinstance(n[k], str) or len(n[k]) > MAX_TEXT):
            raise PatchError("invalid node text")
    if not n.get("title", "").strip():
        raise PatchError("empty node title")
    for k in ("x", "y"):
        if isinstance(n.get(k), bool) or not isinstance(n.get(k), (int, float)) or not math.isfinite(n[k]) or n[k] != round(n[k]):
            raise PatchError("node position must be a finite integer")
    if n.get("parentId") and existing.get(n["parentId"], {}).get("kind") != "subflow":
        raise PatchError("parent must be an existing subflow")
    return n


def validate_flow(flow: Any) -> dict[str, Any]:
    """Validate new full-flow JSON before touching the owner's store."""
    import re
    if not isinstance(flow, dict) or not re.fullmatch(r"flow_[A-Za-z0-9_-]{8,80}", str(flow.get("id", ""))):
        raise PatchError("invalid flow id")
    if not isinstance(flow.get("name"), str) or not flow["name"].strip() or len(flow["name"]) > MAX_TEXT:
        raise PatchError("invalid flow name")
    if not isinstance(flow.get("description", ""), str) or len(flow.get("description", "")) > MAX_TEXT:
        raise PatchError("invalid flow description")
    if not isinstance(flow.get("nodes"), list) or not 2 <= len(flow["nodes"]) <= 100:
        raise PatchError("invalid nodes")
    seen = {}
    for n in flow["nodes"]:
        checked = validate_node(n, seen)
        seen[checked["id"]] = checked
    if sum(n["kind"] == "start" for n in seen.values()) != 1 or sum(n["kind"] == "end" for n in seen.values()) != 1:
        raise PatchError("exactly one start and end required")
    edges = flow.get("edges")
    if not isinstance(edges, list) or len(edges) > 100:
        raise PatchError("invalid edges")
    snap = {"nodes": list(seen.values()), "edges": []}
    ids = set()
    for edge in edges:
        if not isinstance(edge, dict) or not edge.get("id") or edge["id"] in ids:
            raise PatchError("invalid or duplicate edge id")
        ids.add(edge["id"])
        plan = plan_patch(snap, [{"op": "add_edge", "source": edge.get("source"), "target": edge.get("target")}])
        snap = plan["expected"]
        snap["edges"][-1]["id"] = edge["id"]
    # Flat paths and each subflow's interior must have no islands or cycles.
    for scope in [None] + [n["id"] for n in seen.values() if n["kind"] == "subflow"]:
        group = {k for k,n in seen.items() if (n.get("parentId") or None) == scope}
        incoming = {e["target"] for e in edges if e["source"] in group and e["target"] in group}
        roots = group - incoming
        if len(roots) != 1:
            raise PatchError("flow must be a single path per scope")
        visited = set(); cur = next(iter(roots))
        while cur not in visited:
            visited.add(cur)
            nxt = [e["target"] for e in edges if e["source"] == cur and e["target"] in group]
            if not nxt: break
            cur = nxt[0]
        if visited != group:
            raise PatchError("flow contains islands or cycles")
    return {"id": flow["id"], "name": flow["name"], "description": flow.get("description", ""), **snap}


def native_flow(flow: dict[str, Any]) -> dict[str, Any]:
    """Convert the public flat input to FlowForge's stored shape."""
    return {**flow, "nodes": [
        {"id": n["id"], **({"parentId": n["parentId"]} if n.get("parentId") else {}),
         "position": {"x": n["x"], "y": n["y"]},
         "data": {k:v for k,v in n.items() if k not in {"id", "parentId", "x", "y"}}}
        for n in flow["nodes"]]}


def plan_patch(snap: dict[str, Any], ops: list[dict[str, Any]]) -> dict[str, Any]:
    """操作の列を点検し、実行する手順と「実行後こうなるはず」を返す。問題があれば PatchError。

    ops:
      {"op": "update_node", "id": "...", "patch": {"description": "..."}}
      {"op": "add_edge", "source": "...", "target": "...", "replace": false}
      {"op": "remove_edge", "id": "..."}  または  {"op": "remove_edge", "source": "...", "target": "..."}
    """
    if not isinstance(ops, list) or not ops:
        raise PatchError("操作が空です")
    if len(ops) > MAX_OPS:
        raise PatchError(f"操作が多すぎます（{len(ops)}件。{MAX_OPS}件まで）")

    # 計画は写しの上で進める（前の操作の結果を次の操作が見る）
    work = {
        "nodes": [dict(n) for n in snap.get("nodes", [])],
        "edges": [dict(e) for e in snap.get("edges", [])],
    }
    steps: list[dict[str, Any]] = []
    notes: list[str] = []
    new_seq = 0

    for i, op in enumerate(ops, 1):
        kind = op.get("op") if isinstance(op, dict) else None
        nodes = node_map(work)
        if kind == "add_node":
            n = validate_node(op.get("node"), nodes)
            work["nodes"].append(n)
            steps.append({"op": "add_node", "node": n})
        elif kind == "remove_node":
            nid = str(op.get("id") or "")
            if nid not in nodes or nodes[nid].get("kind") in {"start","end"}:
                raise PatchError("cannot remove missing/start/end node")
            if any(e["source"] == nid or e["target"] == nid for e in work["edges"]):
                raise PatchError("remove incident edges explicitly before removing a node")
            if any(n.get("parentId") == nid for n in work["nodes"]):
                raise PatchError("remove subflow children explicitly first")
            work["nodes"] = [n for n in work["nodes"] if n["id"] != nid]
            steps.append({"op":"remove_node","id":nid})
        elif kind == "update_node":
            nid = str(op.get("id") or "")
            if nid not in nodes:
                raise PatchError(f"{i}件目: ノードが見つかりません（{nid}）")
            patch = op.get("patch")
            if not isinstance(patch, dict) or not patch:
                raise PatchError(f"{i}件目: patch が空です")
            bad = [k for k in patch if k not in PATCHABLE_KEYS]
            if bad:
                raise PatchError(f"{i}件目: 書き換えられない項目です（{', '.join(bad)}）。使えるのは {', '.join(PATCHABLE_KEYS)}")
            for k, v in patch.items():
                if not isinstance(v, str):
                    raise PatchError(f"{i}件目: {k} は文字列で指定してください")
                if len(v) > MAX_TEXT:
                    raise PatchError(f"{i}件目: {k} が長すぎます（{len(v)}文字）")
            if "title" in patch and not patch["title"].strip():
                raise PatchError(f"{i}件目: title を空にはできません")
            for n in work["nodes"]:
                if n["id"] == nid:
                    n.update(patch)
            steps.append({"op": "update_node", "id": nid, "patch": dict(patch)})

        elif kind == "add_edge":
            src, tgt = str(op.get("source") or ""), str(op.get("target") or "")
            if src not in nodes or tgt not in nodes:
                raise PatchError(f"{i}件目: 始点か終点のノードが見つかりません（{src} → {tgt}）")
            u, f, _inner = lifted(nodes, src, tgt)
            if u == f:
                raise PatchError(f"{i}件目: 始点と終点が同じになります（{title_of(work, u)}）")
            if nodes[f].get("kind") == "start" or f == "start":
                raise PatchError(f"{i}件目: 開始ノードへ入る矢印は足せません")
            if nodes[u].get("kind") == "end" or u == "end":
                raise PatchError(f"{i}件目: 終了ノードから出る矢印は足せません")
            if any(e["source"] == u and e["target"] == f for e in work["edges"]):
                notes.append(f"{i}件目: すでにある矢印です（{title_of(work, u)} → {title_of(work, f)}）。何もしません")
                continue
            conflicts = edge_conflicts(work, src, tgt)
            if conflicts and op.get("replace") is not True:
                names = "、".join(edge_label(work, e) for e in conflicts)
                raise PatchError(
                    f"{i}件目: この矢印を足すと、既存の矢印が外れます（{names}）。"
                    "FlowForge は1つのノードに矢印を入り1本・出1本しか持てません。"
                    "置き換えてよい時だけ replace=true を付けてください"
                )
            gone = {e["id"] for e in conflicts}
            work["edges"] = [e for e in work["edges"] if e["id"] not in gone]
            new_seq += 1
            work["edges"].append({"id": f"__new_{new_seq}", "source": u, "target": f})
            if (u, f) != (src, tgt):
                notes.append(
                    f"{i}件目: サブフローをまたぐため、矢印は「{title_of(work, u)} → {title_of(work, f)}」として付きます"
                )
            steps.append({"op": "add_edge", "source": u, "target": f, "replaces": sorted(gone)})

        elif kind == "remove_edge":
            eid = str(op.get("id") or "")
            if eid:
                hit = [e for e in work["edges"] if e["id"] == eid]
            else:
                src, tgt = str(op.get("source") or ""), str(op.get("target") or "")
                hit = [e for e in work["edges"] if e["source"] == src and e["target"] == tgt]
            if len(hit) != 1:
                raise PatchError(f"{i}件目: 外す矢印を1本に特定できません（{len(hit)}本）")
            if hit[0]["id"].startswith("__new_"):
                raise PatchError(f"{i}件目: 同じ依頼の中で足した矢印は外せません")
            work["edges"] = [e for e in work["edges"] if e["id"] != hit[0]["id"]]
            steps.append({"op": "remove_edge", "id": hit[0]["id"]})

        else:
            raise PatchError(f"{i}件目: 知らない操作です（{kind}）。使えるのは update_node / add_edge / remove_edge")

    if not steps:
        raise PatchError("実行する操作がありません（" + " / ".join(notes) + "）" if notes else "実行する操作がありません")
    return {"steps": steps, "expected": work, "notes": notes}


# ---------- 検証 ----------

def _edge_pairs(snap: dict[str, Any]) -> list[tuple[str, str]]:
    return sorted((e["source"], e["target"]) for e in snap.get("edges", []))


def compare_to_expected(expected: dict[str, Any], actual: dict[str, Any]) -> list[str]:
    """実行後の状態が計画どおりか。違いを日本語で返す（空なら一致）。"""
    diffs: list[str] = []
    exp_nodes, act_nodes = node_map(expected), node_map(actual)
    for nid in exp_nodes.keys() - act_nodes.keys():
        diffs.append(f"ノードが消えた: {title_of(expected, nid)}")
    for nid in act_nodes.keys() - exp_nodes.keys():
        diffs.append(f"ノードが増えた: {title_of(actual, nid)}")
    for nid in exp_nodes.keys() & act_nodes.keys():
        e, a = exp_nodes[nid], act_nodes[nid]
        for k in ("kind", "subtype", "parentId", "x", "y", *PATCHABLE_KEYS):
            if (e.get(k) or None) != (a.get(k) or None):
                diffs.append(f"ノード「{title_of(expected, nid)}」の {k} が計画と違う")
    ep, ap = _edge_pairs(expected), _edge_pairs(actual)
    for s, t in ap:
        if (s, t) not in ep:
            diffs.append(f"矢印が余分に増えた: {title_of(actual, s)} → {title_of(actual, t)}")
    for s, t in ep:
        if (s, t) not in ap:
            diffs.append(f"矢印が足りない: {title_of(expected, s)} → {title_of(expected, t)}")
    return diffs


def same_state(a: dict[str, Any], b: dict[str, Any]) -> bool:
    """元に戻せたか（ノードと矢印が完全に同じか。矢印は ID も比べる）。"""
    def norm(s: dict[str, Any]) -> str:
        return json.dumps(
            {
                "nodes": sorted(s.get("nodes", []), key=lambda n: n["id"]),
                "edges": sorted(s.get("edges", []), key=lambda e: e["id"]),
            },
            ensure_ascii=False,
            sort_keys=True,
        )

    return norm(a) == norm(b)


def summarize_change(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    """結果に残す差分（人と ChatGPT が読む）。"""
    bn, an = node_map(before), node_map(after)
    bp, ap = _edge_pairs(before), _edge_pairs(after)
    changed = []
    for nid in bn.keys() & an.keys():
        keys = [k for k in PATCHABLE_KEYS if (bn[nid].get(k) or None) != (an[nid].get(k) or None)]
        if keys:
            changed.append({"node": title_of(after, nid), "id": nid, "fields": keys})
    return {
        "nodes_before": len(bn),
        "nodes_after": len(an),
        "nodes_changed": changed,
        "nodes_added": [title_of(after, i) for i in an.keys() - bn.keys()],
        "nodes_removed": [title_of(before, i) for i in bn.keys() - an.keys()],
        "edges_added": [f"{title_of(after, s)} → {title_of(after, t)}" for s, t in ap if (s, t) not in bp],
        "edges_removed": [f"{title_of(before, s)} → {title_of(before, t)}" for s, t in bp if (s, t) not in ap],
    }


# ---------- ページへ入れる JS（ページ本体の世界で動かす） ----------

# 画面の React の内部から、フローを保存している部品（zustand の api）を探す
JS_FIND_API = r"""
function __ffApi(){
  function rootFiber(){
    var els=document.querySelectorAll('body, body *');
    for(var i=0;i<els.length;i++){ var el=els[i];
      for(var k in el){ if(k.indexOf('__reactContainer$')===0||k.indexOf('__reactFiber$')===0) return el[k]; } }
    return null;
  }
  function isApi(v){
    if(!v||typeof v!=='object'||typeof v.getState!=='function'||typeof v.setState!=='function') return false;
    try{ var s=v.getState();
      return !!(s&&s.flows&&typeof s.updateNodeData==='function'&&typeof s.addEdge==='function'
        &&typeof s.removeEdge==='function'&&typeof s.runWithHistoryEntry==='function'&&typeof s.undo==='function');
    }catch(e){ return false; }
  }
  var f=rootFiber(); if(!f) return null;
  while(f.return) f=f.return;
  var seen=0, api=null, stack=[f];
  function check(v,depth){
    if(api||!v||typeof v!=='object'||v.$$typeof||(v instanceof Node)) return;
    if(isApi(v)){ api=v; return; }
    if(depth>=2) return;
    var keys; try{ keys=Object.keys(v); }catch(e){ return; }
    if(keys.length>40) return;
    for(var i=0;i<keys.length&&!api;i++){ var c; try{ c=v[keys[i]]; }catch(e){ continue; } check(c,depth+1); }
  }
  while(stack.length&&seen<50000&&!api){
    var n=stack.pop(); seen++;
    var h=n.memoizedState, hi=0;
    while(h&&typeof h==='object'&&hi<120&&!api){ check(h.memoizedState,0); if(h.queue) check(h.queue,0); h=h.next; hi++; }
    check(n.memoizedProps,0);
    if(n.child) stack.push(n.child);
    if(n.sibling) stack.push(n.sibling);
  }
  return api;
}
function __ffSnap(api,fid){
  var f=api.getState().flows[fid]; if(!f) return null;
  return {id:f.id,name:f.name,description:f.description||'',updatedAt:f.updatedAt,
    history:(api.getState().history[fid]||[]).length,
    historyTop:(function(h){return h.length?String(h[h.length-1].label||''):'';})(api.getState().history[fid]||[]),
    nodes:f.nodes.map(function(n){var d=n.data||{};return {id:n.id,parentId:n.parentId||null,kind:d.kind||null,subtype:d.subtype||null,
      title:d.title||'',description:d.description||'',meta:d.meta||'',toolName:d.toolName||'',
      x:n.position?Math.round(n.position.x):null,y:n.position?Math.round(n.position.y):null};}),
    edges:f.edges.map(function(e){return {id:e.id,source:e.source,target:e.target};})};
}
"""


def js_snapshot(fid: str) -> str:
    """今の状態を読む式（読むだけ）。"""
    return (
        "(function(){" + JS_FIND_API + "var api=__ffApi(); if(!api) return JSON.stringify({ok:false,error:'store_not_found'});"
        f"var s=__ffSnap(api,{json.dumps(fid)}); if(!s) return JSON.stringify({{ok:false,error:'flow_not_in_store'}});"
        "return JSON.stringify({ok:true,snap:s});})()"
    )


def js_apply(fid: str, steps: list[dict[str, Any]], label: str) -> str:
    """計画済みの手順を、履歴1件ぶんとして実行する式。"""
    return (
        "(function(){" + JS_FIND_API + "var api=__ffApi(); if(!api) return JSON.stringify({ok:false,error:'store_not_found'});"
        f"var fid={json.dumps(fid)}, steps={json.dumps(steps, ensure_ascii=False)}, done=0, err=null;"
        "if(!api.getState().flows[fid]) return JSON.stringify({ok:false,error:'flow_not_in_store'});"
        f"api.getState().runWithHistoryEntry(fid,{json.dumps(label, ensure_ascii=False)},function(){{"
        "try{ for(var i=0;i<steps.length;i++){ var st=steps[i], s=api.getState();"
        "if(st.op==='update_node'){ s.updateNodeData(fid,st.id,st.patch); }"
        "else if(st.op==='add_node'){ var f=JSON.parse(JSON.stringify(s.flows[fid])); var n=st.node;"
        "if(f.nodes.some(function(v){return v.id===n.id;})) throw new Error('node_exists');"
        "var data={}; Object.keys(n).forEach(function(k){if(['id','parentId','x','y'].indexOf(k)<0)data[k]=n[k];});"
        "f.nodes.push({id:n.id,parentId:n.parentId||undefined,position:{x:n.x,y:n.y},data:data});"
        "f.updatedAt=new Date().toISOString();s.loadFlow(f); }"
        "else if(st.op==='remove_node'){var f=JSON.parse(JSON.stringify(s.flows[fid]));"
        "if(f.nodes.some(function(n){return n.parentId===st.id;})||f.edges.some(function(e){return e.source===st.id||e.target===st.id;}))throw new Error('node_has_links');"
        "f.nodes=f.nodes.filter(function(n){return n.id!==st.id;});f.updatedAt=new Date().toISOString();s.loadFlow(f); }"
        "else if(st.op==='add_edge'){ s.addEdge(fid,{source:st.source,target:st.target}); }"
        "else if(st.op==='remove_edge'){ s.removeEdge(fid,st.id); }"
        "else { throw new Error('unknown op '+st.op); } done++; } }catch(e){ err=String(e); }"
        "});"
        "return JSON.stringify({ok:!err,done:done,error:err,snap:__ffSnap(api,fid)});})()"
    )


def js_undo_once(fid: str) -> str:
    """履歴を1件戻す式（直接編集は履歴1件なので、これで実行前に戻る）。"""
    return (
        "(function(){" + JS_FIND_API + "var api=__ffApi(); if(!api) return JSON.stringify({ok:false,error:'store_not_found'});"
        f"var fid={json.dumps(fid)}; var r=api.getState().undo(fid);"
        "return JSON.stringify({ok:!!r,snap:__ffSnap(api,fid)});})()"
    )


# ---------- 古いタブの検知（複数タブでの上書き防止） ----------
#
# FlowForge は、タブごとに「全フローの内容」をメモリに持ち、何か編集するたびに全フローをまとめて
# ブラウザ（localStorage）へ保存する。タブ同士で内容を合わせる仕組みは無いので、古いタブで編集すると、
# 他のタブで直したフローが古い内容で上書きされる。編集の直前に、タブのメモリと保存内容を比べる。

def stale_reasons(memory: dict[str, str | None], stored: dict[str, str | None]) -> list[str]:
    """タブのメモリ（id→更新日時）と、ブラウザの保存内容（id→更新日時）の食い違い。空なら最新。"""
    out: list[str] = []
    for fid in sorted(stored.keys() - memory.keys()):
        out.append(f"このタブが知らないフローが保存されている（{fid}）")
    for fid in sorted(memory.keys() - stored.keys()):
        out.append(f"このタブにだけあるフローがある（{fid}）")
    for fid in sorted(memory.keys() & stored.keys()):
        if memory[fid] != stored[fid]:
            out.append(f"更新日時が違う（{fid}: タブ {memory[fid]} ／ 保存 {stored[fid]}）")
    return out


def js_freshness() -> str:
    """タブのメモリと保存内容の、フローごとの更新日時を読む式（読むだけ）。"""
    return (
        "(function(){" + JS_FIND_API + "var api=__ffApi(); if(!api) return JSON.stringify({ok:false,error:'store_not_found'});"
        "var mem={}, f=api.getState().flows; Object.keys(f).forEach(function(k){mem[k]=f[k].updatedAt||null;});"
        "var st={}; try{ var raw=JSON.parse(localStorage.getItem('flowforge:flows')||'null');"
        "var fl=raw&&raw.state&&raw.state.flows||{}; Object.keys(fl).forEach(function(k){st[k]=fl[k].updatedAt||null;}); }"
        "catch(e){ return JSON.stringify({ok:false,error:'storage_unreadable'}); }"
        "return JSON.stringify({ok:true,memory:mem,stored:st});})()"
    )
