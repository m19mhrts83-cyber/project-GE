#!/usr/bin/env python3
"""FlowForge のフローを、置き場（Chrome の既定プロフィール）へ移す（2026-11-21）。

FlowForge は「最初に保存したブラウザ」をフローの持ち主として扱う。ChatGPT から編集できるのは、
置き場のブラウザにあるフローだけなので、社員ごとに1回、共有リンクから置き場へコピーする。
コピーすると ID が変わるので、registry などの登録も付け替える。

やること（AI は呼ばない）:
  1. 登録されている共有リンクから、今のフローを読む
  2. 置き場の Chrome で /flows/import/<共有ID> を開く（＝「このフローを自分の作業用にコピー」と同じ）
  3. 新しくできたフローの中身が、元と同じかを照合する
  4. 新しいフローの共有リンクを発行する（画面の「フローを共有」を押す。閲覧専用・一覧には載せない）
  5. --write-repo の時だけ、この checkout の registry・共有リンク一覧・資料の ID を付け替える

使い方（必ず worktree で。~/git-repos の本体では --write-repo を使わない）:
  python scripts/jarvis_flowforge_migrate_to_home.py --agent 315 --dry-run     # 何も作らず、状況だけ確かめる
  python scripts/jarvis_flowforge_migrate_to_home.py --agent 315               # コピーして照合し、共有リンクを発行
  python scripts/jarvis_flowforge_migrate_to_home.py --agent 315 --write-repo  # 上に加えて登録を付け替える
  python scripts/jarvis_flowforge_migrate_to_home.py --agent 315 --write-repo --new-flow-id flow_… --new-share-url https://…
      # コピー済みのフローについて、登録の付け替えだけ行う

安全:
  - 元のフロー（Cursor 側など）には触れない。消さない
  - 置き場に同じ内容のコピーがすでにあれば、作らずに止まる（二重コピー防止）
  - 「みんなのフローに載せる」は押さない
  - 持ち主でないブラウザで編集 URL を開かない（開くのは import の URL と、新しくできた自分のフローだけ）
詳細: docs/AIエージェントチーム/54b_FlowForge読取プロキシ_OpenAPI_20261106.md
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
import jarvis_flowforge_assistant_paste as ff  # noqa: E402
import jarvis_flowforge_share_fetch as share  # noqa: E402

TEAM_JSON = REPO / "apps" / "jarvis-dashboard" / "data" / "agentTeam.json"
SHARE_CONFIG = REPO / "config" / "flowforge_share_urls.json"
HUB = REPO / "docs" / "AIエージェントチーム"


# ---------- 純粋な部分（テストできる） ----------

def normalize(nodes: list[dict[str, Any]], edges: list[dict[str, Any]]) -> dict[str, Any]:
    """照合用の形。位置や見た目は比べない（コピーで変わらないはずだが、意味に関係しない）。"""
    out_nodes = []
    for n in nodes:
        d = n.get("data") or n
        out_nodes.append({
            "id": n.get("id"),
            "parentId": n.get("parentId") or None,
            "kind": d.get("kind"),
            "subtype": d.get("subtype") or None,
            "title": d.get("title") or "",
            "description": d.get("description") or "",
            "meta": d.get("meta") or "",
            "toolName": d.get("toolName") or "",
        })
    return {
        "nodes": sorted(out_nodes, key=lambda x: str(x["id"])),
        "edges": sorted((e.get("source"), e.get("target")) for e in edges),
    }


def content_diffs(src: dict[str, Any], dst: dict[str, Any]) -> list[str]:
    """元（共有リンク）とコピーの違い。空なら同じ内容。"""
    diffs: list[str] = []
    s_nodes = {n["id"]: n for n in src["nodes"]}
    d_nodes = {n["id"]: n for n in dst["nodes"]}
    for nid in sorted(s_nodes.keys() - d_nodes.keys()):
        diffs.append(f"コピーに無いノード: {s_nodes[nid]['title'] or nid}")
    for nid in sorted(d_nodes.keys() - s_nodes.keys()):
        diffs.append(f"コピーにだけあるノード: {d_nodes[nid]['title'] or nid}")
    for nid in sorted(s_nodes.keys() & d_nodes.keys()):
        for k in ("parentId", "kind", "subtype", "title", "description", "meta", "toolName"):
            if s_nodes[nid][k] != d_nodes[nid][k]:
                diffs.append(f"ノード「{s_nodes[nid]['title'] or nid}」の {k} が違う")
    s_edges, d_edges = list(src["edges"]), list(dst["edges"])
    for e in s_edges:
        if e not in d_edges:
            diffs.append(f"コピーに無い矢印: {e[0]} → {e[1]}")
    for e in d_edges:
        if e not in s_edges:
            diffs.append(f"コピーにだけある矢印: {e[0]} → {e[1]}")
    return diffs


def rewrite_share_config(text: str, agent_id: str, new_flow_id: str, new_share_url: str) -> str:
    """共有リンク一覧（JSON）の、社員の共有リンクと新しいフロー ID の行を付け替える。"""
    data = json.loads(text)
    data.setdefault("by_agent_id", {})[agent_id] = new_share_url
    by_flow = data.setdefault("by_flow_id", {})
    by_flow = {new_flow_id: new_share_url, **{k: v for k, v in by_flow.items() if k != new_flow_id}}
    data["by_flow_id"] = by_flow
    return json.dumps(data, ensure_ascii=False, indent=2) + "\n"


# ---------- ブラウザ ----------

JS_LIST = """
(function(){try{
  var raw=JSON.parse(localStorage.getItem('flowforge:flows')||'null');
  var fl=raw&&raw.state&&raw.state.flows||{};
  return JSON.stringify({ok:true,flows:Object.keys(fl).map(function(k){var f=fl[k];
    return {id:k,name:f.name,nodes:(f.nodes||[]).length,edges:(f.edges||[]).length,createdAt:f.createdAt};})});
}catch(e){return JSON.stringify({ok:false,error:String(e)});}})()
"""

JS_FLOW = """
(function(){try{
  var raw=JSON.parse(localStorage.getItem('flowforge:flows')||'null');
  var f=raw&&raw.state&&raw.state.flows&&raw.state.flows[%s];
  if(!f) return JSON.stringify({ok:false,error:'not_found'});
  return JSON.stringify({ok:true,name:f.name,nodes:f.nodes,edges:f.edges});
}catch(e){return JSON.stringify({ok:false,error:String(e)});}})()
"""

JS_CLICK_SHARE = """
(function(){
  var b=[].slice.call(document.querySelectorAll('button')).filter(function(b){
    return ((b.innerText||'')+(b.getAttribute('aria-label')||'')).indexOf('フローを共有')>=0;})[0];
  if(!b) return 'no_button'; if(b.disabled) return 'disabled'; b.click(); return 'clicked';
})()
"""

JS_READ_SHARE = """
(function(){
  var hit='';
  [].slice.call(document.querySelectorAll('input,textarea')).forEach(function(el){
    if(!hit&&(el.value||'').indexOf('/share/')>=0) hit=el.value;});
  return hit;
})()
"""

JS_CLOSE_DIALOG = """
(function(){
  var b=[].slice.call(document.querySelectorAll('button')).filter(function(b){
    return (b.innerText||'').replace(/\\s/g,'')==='閉じる';})[0];
  if(!b) return 'no_button'; b.click(); return 'closed';
})()
"""


def home_tab() -> tuple[int, int]:
    """置き場のプロフィールの FlowForge のタブ（読めるもの）。無ければトップを開く。"""
    def look() -> tuple[int, int] | None:
        try:
            tabs = ff.find_tabs(ff.BASE)
        except Exception:
            return None
        for t in tabs:
            try:
                got = json.loads(ff.run_js(*t, JS_LIST))
            except Exception:
                continue  # 別プロフィール（許可設定がオフ）
            if got.get("ok"):
                return t
        return None

    tab = look()
    if tab is None:
        ff.open_in_home_profile(ff.BASE + "/")
        time.sleep(6)
        tab = look()
    if tab is None:
        raise SystemExit("置き場の Chrome で FlowForge を読めません。Chrome の「Apple Events からの JavaScript を許可」を確かめてください。")
    return tab


def list_flows(tab: tuple[int, int]) -> list[dict[str, Any]]:
    got = json.loads(ff.run_js(*tab, JS_LIST))
    if not got.get("ok"):
        raise SystemExit(f"保存内容を読めません: {got.get('error')}")
    return got["flows"]


def issue_share(fid: str) -> str:
    """新しいフローの編集画面で「フローを共有」を押し、共有 URL を読む。"""
    tab = next(iter(ff.find_tabs(f"/flows/{fid}")), None)
    if tab is None:
        raise SystemExit("新しいフローの編集タブが見つかりません")
    res = ff.run_js(*tab, JS_CLICK_SHARE)
    if res != "clicked":
        raise SystemExit(f"「フローを共有」を押せませんでした（{res}）")
    url = ""
    for _ in range(15):
        time.sleep(1.5)
        url = ff.run_js(*tab, JS_READ_SHARE)
        if "/share/" in url:
            break
    ff.run_js(*tab, JS_CLOSE_DIALOG)
    if "/share/" not in url:
        raise SystemExit("共有 URL を読めませんでした。画面で「フローを共有」を押して確かめてください")
    return url.strip()


# ---------- 登録の付け替え ----------

def write_repo(agent_id: str, old_id: str, new_id: str, new_share_url: str) -> list[str]:
    if REPO.resolve() == (Path.home() / "git-repos").resolve():
        raise SystemExit("~/git-repos の本体では付け替えません。worktree で実行してください。")
    changed: list[str] = []
    for path in list(HUB.rglob("*.md")) + [HUB / "agents_registry.yaml"]:
        if "memory" in path.parts or not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except Exception:
            continue
        if old_id in text:
            path.write_text(text.replace(old_id, new_id), encoding="utf-8")
            changed.append(str(path.relative_to(REPO)))
    SHARE_CONFIG.write_text(
        rewrite_share_config(SHARE_CONFIG.read_text(encoding="utf-8"), agent_id, new_id, new_share_url),
        encoding="utf-8",
    )
    changed.append(str(SHARE_CONFIG.relative_to(REPO)))
    return changed


def main() -> int:
    ap = argparse.ArgumentParser(description="FlowForge のフローを置き場の Chrome へ移す")
    ap.add_argument("--agent", required=True, help="社員番号（例: 315）")
    ap.add_argument("--dry-run", action="store_true", help="何も作らず、状況だけ確かめる")
    ap.add_argument("--write-repo", action="store_true", help="この checkout の登録を付け替える（worktree で）")
    ap.add_argument("--new-flow-id", help="コピー済みの新しいフロー ID（付け替えだけ行う時）")
    ap.add_argument("--new-share-url", help="コピー済みの新しい共有 URL（付け替えだけ行う時）")
    args = ap.parse_args()

    team = json.loads(TEAM_JSON.read_text(encoding="utf-8"))
    agent = next((a for a in team["agents"] if a["id"] == args.agent), None)
    if not agent or not agent.get("flowforge_id"):
        raise SystemExit(f"社員 {args.agent} の flowforge_id が登録にありません")
    old_id = agent["flowforge_id"]

    if args.new_flow_id or args.new_share_url:
        if not (args.write_repo and args.new_flow_id and args.new_share_url):
            ap.error("--new-flow-id と --new-share-url は、--write-repo と3つ一緒に指定します")
        changed = write_repo(args.agent, old_id, args.new_flow_id, args.new_share_url)
        print(json.dumps({"agent": args.agent, "old_flow_id": old_id, "new_flow_id": args.new_flow_id, "changed": changed}, ensure_ascii=False, indent=1))
        return 0

    share_url = agent.get("flowforge_share_url") or ""
    if "/share/" not in share_url:
        raise SystemExit(
            f"社員 {args.agent} は共有リンクが登録されていません。持ち主のブラウザで「フローを共有」を押し、"
            "config/flowforge_share_urls.json に登録してから実行してください。"
        )
    share_id = share.share_id_from_url(share_url)
    payload = share.fetch_share(ff.BASE, share_id, 25.0)
    src_flow = payload.get("flow") or {}
    if src_flow.get("id") != old_id:
        raise SystemExit(
            f"共有リンクが指すフロー（{src_flow.get('id')}）が、登録の flowforge_id（{old_id}）と違います。"
            "正しい共有リンクを登録し直してください。"
        )
    src = normalize(src_flow.get("nodes") or [], src_flow.get("edges") or [])

    tab = home_tab()
    before = list_flows(tab)
    info = {
        "agent": args.agent,
        "name": src_flow.get("name"),
        "old_flow_id": old_id,
        "source_nodes": len(src["nodes"]),
        "source_edges": len(src["edges"]),
        "source_updatedAt": src_flow.get("updatedAt"),
        "home_flows": len(before),
    }
    if any(f["id"] == old_id for f in before):
        raise SystemExit(f"このフローは、すでに置き場にあります（{old_id}）。移す必要はありません。")
    same = [f for f in before if f["name"] == src_flow.get("name") and f["nodes"] == len(src["nodes"]) and f["edges"] == len(src["edges"])]
    if same:
        raise SystemExit(
            "置き場に、同じ名前・同じ大きさのフローがすでにあります。二重コピーを避けるため止めます: "
            + ", ".join(f["id"] for f in same)
            + "\nコピー済みなら --write-repo --new-flow-id … --new-share-url … で付け替えだけ行えます。"
        )
    if args.dry_run:
        info["dry_run"] = True
        print(json.dumps(info, ensure_ascii=False, indent=1))
        return 0

    # コピー（＝「このフローを自分の作業用にコピー」）
    known = {f["id"] for f in before}
    ff.open_in_home_profile(f"{ff.BASE}/flows/import/{share_id}")
    new = None
    for _ in range(15):
        time.sleep(2)
        tab = home_tab()
        fresh = [f for f in list_flows(tab) if f["id"] not in known]
        if fresh:
            new = fresh[0]
            break
    if new is None:
        raise SystemExit("コピーができたことを確かめられませんでした。置き場の Chrome の画面を見てください。")
    new_id = new["id"]

    got = json.loads(ff.run_js(*tab, JS_FLOW % json.dumps(new_id)))
    if not got.get("ok"):
        raise SystemExit(f"コピーの中身を読めません: {got.get('error')}")
    diffs = content_diffs(src, normalize(got["nodes"], got["edges"]))
    info.update({"new_flow_id": new_id, "new_edit_url": f"{ff.BASE}/flows/{new_id}", "verified": not diffs})
    if diffs:
        info["diffs"] = diffs[:20]
        print(json.dumps(info, ensure_ascii=False, indent=1))
        print("コピーの中身が元と違います。登録は付け替えません。コピーは置き場に残っています。")
        return 2

    time.sleep(3)  # 編集画面の読み込みを待つ
    info["new_share_url"] = issue_share(new_id)
    if args.write_repo:
        info["changed"] = write_repo(args.agent, old_id, new_id, info["new_share_url"])
        info["next"] = "status_sync（--no-drive）で agentTeam.json を作り直し、意図したファイルだけを PR にする"
    print(json.dumps(info, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
