#!/usr/bin/env python3
"""FlowForge の AIアシスタントへ修正文を入力する（試作・2026-11-21）。

AI は呼ばない「プログラム」。本人の Google Chrome で開いている FlowForge のタブに、
AppleScript 経由で JavaScript を実行して入力欄へ文を入れる。

前提:
  - Chrome の「表示 > 開発 / 管理 > Apple Events からの JavaScript を許可」をオン
  - フローの持ち主のブラウザ（最初に保存した Chrome プロフィール）で動かす
  - 既定は入力だけ（送信しない）。--send を付けた時だけ「送信」を押す

安全:
  - 持ち主でないブラウザで /flows/<id> を開くと、空の「新しいフロー」が同じ ID で
    作られてしまう。そのため、先に FlowForge のトップで保存内容を確かめ、
    対象フローが無いブラウザでは編集画面を開かずに止める。
  - 匿名 ID・cookie は読まないし表示しない。

使い方:
  python scripts/jarvis_flowforge_assistant_paste.py --agent 311 --check
  python scripts/jarvis_flowforge_assistant_paste.py --agent 311 --text-file 修正文.txt
  python scripts/jarvis_flowforge_assistant_paste.py --agent 311 --text-file 修正文.txt --send
  python scripts/jarvis_flowforge_assistant_paste.py --agent 311 --undo 1      # 「元に戻す」を1回

待ち箱（ChatGPT が MCP の queue_flowforge_edit で置いた、本人了承済みの修正文）:
  python scripts/jarvis_flowforge_assistant_paste.py --queue-list
  python scripts/jarvis_flowforge_assistant_paste.py --queue-once     # 1件拾って送信し、結果を書き戻す
  （JARVIS_SUPABASE_URL / JARVIS_SUPABASE_SERVICE_ROLE_KEY は環境変数か .env.jarvis_private）
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
BASE = "https://flowforge-259747770348.asia-northeast1.run.app"
TEAM_JSON = REPO / "apps" / "jarvis-dashboard" / "data" / "agentTeam.json"
MAX_CHARS = 2000
QUEUE_TABLE = "flowforge_edit_queue"
REPLY_WAIT_SEC = 120


def flow_id_for_agent(agent_id: str) -> str:
    data = json.loads(TEAM_JSON.read_text(encoding="utf-8"))
    for a in data.get("agents", []):
        if a.get("id") == agent_id and a.get("flowforge_id"):
            return str(a["flowforge_id"])
    raise SystemExit(f"flowforge_id が見つかりません: agent {agent_id}")


def osa(script: str) -> str:
    r = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.strip() or "osascript failed")
    return r.stdout.strip()


def as_str(s: str) -> str:
    """AppleScript の文字列リテラルへ。"""
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def find_tabs(url_part: str) -> list[tuple[int, int]]:
    """URL に url_part を含むタブをすべて返す（Chrome の全ウィンドウ・全プロフィール）。"""
    out = osa(
        'tell application "Google Chrome"\n'
        '  set hits to ""\n'
        "  repeat with wi from 1 to (count of windows)\n"
        "    repeat with ti from 1 to (count of tabs of window wi)\n"
        f"      if (URL of tab ti of window wi) contains {as_str(url_part)} then\n"
        '        set hits to hits & (wi as text) & "," & (ti as text) & ";"\n'
        "      end if\n"
        "    end repeat\n"
        "  end repeat\n"
        "  return hits\n"
        "end tell"
    )
    tabs = []
    for part in out.split(";"):
        if part.strip():
            w, t = part.split(",")
            tabs.append((int(w), int(t)))
    return tabs


def find_tab(url_part: str) -> tuple[int, int] | None:
    tabs = find_tabs(url_part)
    return tabs[0] if tabs else None


def run_js(win: int, tab: int, js: str) -> str:
    return osa(
        'tell application "Google Chrome" to execute '
        f"tab {tab} of window {win} javascript {as_str(js)}"
    )


def open_tab(url: str) -> None:
    osa(
        'tell application "Google Chrome"\n'
        "  tell front window to make new tab with properties "
        f"{{URL:{as_str(url)}}}\n"
        "end tell"
    )


JS_OWNS = """
(function(){try{
  var raw=JSON.parse(localStorage.getItem('flowforge:flows')||'null');
  var fl=raw&&raw.state&&raw.state.flows||{};
  var f=fl[%(fid)s];
  var t={}; if(f){(f.nodes||[]).forEach(function(n){t[n.id]=(n.data||{}).title||n.id;});}
  return JSON.stringify({ok:true,count:Object.keys(fl).length,has:!!f,
    nodes:f?(f.nodes||[]).length:0,name:f?f.name:null,updatedAt:f?f.updatedAt:null,
    edges:f?(f.edges||[]).map(function(e){return t[e.source]+' → '+t[e.target];}):[],
    titles:f?(f.nodes||[]).map(function(n){return t[n.id];}):[]});
}catch(e){return JSON.stringify({ok:false,error:String(e)});}})()
"""

JS_STATE = """
(function(){
  var ta=document.querySelector('textarea[placeholder*="AI Assistant"]');
  var btn=[].slice.call(document.querySelectorAll('button')).filter(function(b){
    return (b.innerText||'').replace(/\\s/g,'').indexOf('送信')===0;})[0];
  return JSON.stringify({textarea:!!ta,send:!!btn,sendDisabled:btn?btn.disabled:null,
    syncFailed:document.body.innerText.indexOf('同期失敗')>=0});
})()
"""

JS_FILL = """
(function(){
  var ta=document.querySelector('textarea[placeholder*="AI Assistant"]');
  if(!ta) return 'no_textarea';
  var set=Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype,'value').set;
  set.call(ta,%(text)s);
  ta.dispatchEvent(new Event('input',{bubbles:true}));
  ta.focus();
  return 'filled:'+ta.value.length;
})()
"""

JS_SEND = """
(function(){
  var btn=[].slice.call(document.querySelectorAll('button')).filter(function(b){
    return (b.innerText||'').replace(/\\s/g,'').indexOf('送信')===0;})[0];
  if(!btn) return 'no_button';
  if(btn.disabled) return 'disabled';
  btn.click();
  return 'sent';
})()
"""


JS_UNDO = """
(function(){
  var b=[].slice.call(document.querySelectorAll('button')).filter(function(b){
    return ((b.innerText||'')+(b.getAttribute('aria-label')||'')).indexOf('元に戻す')>=0;})[0];
  if(!b) return 'no_button';
  if(b.disabled) return 'disabled';
  b.click();
  return 'clicked';
})()
"""

UNDO_MAX_PRESSES = 6

JS_SNAPSHOT = """
(function(){
  var txt=document.body.innerText||'';
  var a=txt.lastIndexOf('AI Assistant\\n');
  var b=txt.indexOf('\\n送信',a);
  var ta=document.querySelector('textarea[placeholder*="AI Assistant"]');
  return JSON.stringify({len:txt.length,
    reply:(a>=0&&b>a)?txt.slice(a+13,b).trim().slice(0,1500):'',
    inputEmpty:ta?ta.value==='':null,
    syncFailed:txt.indexOf('同期失敗')>=0});
})()
"""


class PasteStop(Exception):
    """安全のために止めた（code は終了コード）。"""

    def __init__(self, code: int, message: str):
        super().__init__(message)
        self.code = code


def flow_counts(tab: tuple[int, int], fid: str) -> dict[str, Any]:
    return json.loads(run_js(*tab, JS_OWNS % {"fid": json.dumps(fid)}))


def prepare(fid: str) -> tuple[tuple[int, int], dict[str, Any]]:
    """持ち主の確認 → 編集画面のタブを返す。持ち主でなければ編集画面を開かない。"""
    edit_part = f"/flows/{fid}"
    # FlowForge のタブは複数のプロフィールにありうる。対象フローを持つタブ（＝持ち主）を探す。
    # 許可設定がオフのプロフィールのタブは読めないので飛ばす。
    candidates = find_tabs(BASE)
    if not candidates:
        open_tab(BASE + "/")
        time.sleep(4)
        candidates = find_tabs(BASE)
    if not candidates:
        raise PasteStop(6, "FlowForge のタブを開けませんでした")
    owner_tab, owns, unreadable = None, {}, 0
    for cand in candidates:
        try:
            got = json.loads(run_js(*cand, JS_OWNS % {"fid": json.dumps(fid)}))
        except Exception:
            unreadable += 1
            continue
        if got.get("ok") and got.get("has") and got.get("nodes", 0) > 2:
            owner_tab, owns = cand, got
            break
        owns = owns or got
    print("持ち主確認:", {k: owns.get(k) for k in ("ok", "count", "has", "nodes", "updatedAt")},
          f"（見たタブ {len(candidates)}・読めないタブ {unreadable}）")
    if owner_tab is None:
        if unreadable == len(candidates):
            raise PasteStop(8, "FlowForge のタブを読めません。置き場の Chrome で「Apple Events からの JavaScript を許可」がオンか確かめてください。")
        raise PasteStop(2, "対象フローの持ち主のタブが見つかりません。編集画面は開かずに止めます。")
    tab = next((t for t in find_tabs(edit_part) if t[0] == owner_tab[0]), None)
    if tab is None and edit_part in osa(
        f'tell application "Google Chrome" to return URL of tab {owner_tab[1]} of window {owner_tab[0]}'
    ):
        tab = owner_tab
    if tab is None:
        # 持ち主のウィンドウの中で開く（別プロフィールで開くと空のフローができる）
        osa(
            'tell application "Google Chrome" to tell window '
            f"{owner_tab[0]} to make new tab with properties {{URL:{as_str(BASE + edit_part)}}}"
        )
        time.sleep(5)
        tab = next((t for t in find_tabs(edit_part) if t[0] == owner_tab[0]), None)
    if tab is None:
        raise PasteStop(6, "編集画面のタブが見つかりません")
    state = json.loads(run_js(*tab, JS_STATE))
    print("画面の状態:", state)
    if state.get("syncFailed"):
        raise PasteStop(3, "画面に「同期失敗」が出ています。止めます。")
    if not state.get("textarea") or not state.get("send"):
        raise PasteStop(4, "AIアシスタントの入力欄か送信ボタンが見つかりません。画面の作りが変わった可能性があります。")
    return tab, owns


def fill(tab: tuple[int, int], text: str) -> None:
    res = run_js(*tab, JS_FILL % {"text": json.dumps(text)})
    print("入力:", res)
    if not res.startswith("filled:"):
        raise PasteStop(4, f"入力できませんでした（{res}）")


def send_and_wait(tab: tuple[int, int], fid: str, before: dict[str, Any]) -> dict[str, Any]:
    """送信し、AIアシスタントの返事が落ち着くまで待つ。前後のノード数などを返す。"""
    time.sleep(0.5)
    res = run_js(*tab, JS_SEND)
    print("送信:", res)
    if res != "sent":
        raise PasteStop(5, f"送信できませんでした（{res}）")
    last_len, stable, snap = -1, 0, {}
    deadline = time.time() + REPLY_WAIT_SEC
    while time.time() < deadline:
        time.sleep(4)
        snap = json.loads(run_js(*tab, JS_SNAPSHOT))
        if snap.get("reply") and snap.get("len") == last_len:
            stable += 1
            if stable >= 2:
                break
        else:
            stable = 0
        last_len = snap.get("len", -1)
    after = flow_counts(tab, fid)
    return {
        "reply": snap.get("reply", ""),
        "reply_settled": stable >= 2,
        "sync_failed": bool(snap.get("syncFailed")),
        **diff_states(before, after),
    }


def list_diff(before: list[str], after: list[str]) -> tuple[list[str], list[str]]:
    """（増えたもの, 消えたもの）。同じ名前が複数あっても数で比べる。"""
    b, a = list(before), list(after)
    for x in list(a):
        if x in b:
            b.remove(x)
            a.remove(x)
    return a, b


def diff_states(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    """送信の前後で、増えた／消えた矢印とノードを出す（頼んでいない変更に気づくため）。"""
    e_add, e_del = list_diff(before.get("edges") or [], after.get("edges") or [])
    n_add, n_del = list_diff(before.get("titles") or [], after.get("titles") or [])
    return {
        "nodes_before": before.get("nodes"),
        "nodes_after": after.get("nodes"),
        "updatedAt_before": before.get("updatedAt"),
        "updatedAt_after": after.get("updatedAt"),
        "changed": before.get("updatedAt") != after.get("updatedAt"),
        "edges_added": e_add,
        "edges_removed": e_del,
        "nodes_added": n_add,
        "nodes_removed": n_del,
    }


def undo_to(tab: tuple[int, int], fid: str, target_updated_at: str | None, presses: int | None) -> dict[str, Any]:
    """「元に戻す」を押す。target_updated_at があれば、その更新日時に戻るまで（最大 UNDO_MAX_PRESSES 回）。"""
    before = flow_counts(tab, fid)
    cur, pressed, stopped = before, 0, ""
    limit = presses if presses else UNDO_MAX_PRESSES
    while pressed < limit:
        if target_updated_at and cur.get("updatedAt") == target_updated_at:
            break
        res = run_js(*tab, JS_UNDO)
        if res != "clicked":
            stopped = res
            break
        pressed += 1
        time.sleep(1.5)
        cur = flow_counts(tab, fid)
    out = diff_states(before, cur)
    out["undo_presses"] = pressed
    out["reached_target"] = (cur.get("updatedAt") == target_updated_at) if target_updated_at else None
    if stopped:
        out["undo_stopped"] = stopped
    return out


# ---------- 待ち箱 ----------

def load_env() -> None:
    """.env.jarvis_private から Supabase の2項目だけ読む（値は表示しない）。"""
    need = ("JARVIS_SUPABASE_URL", "JARVIS_SUPABASE_SERVICE_ROLE_KEY")
    if all(os.environ.get(k) for k in need):
        return
    for env in (REPO / ".env.jarvis_private", Path.home() / "git-repos" / ".env.jarvis_private"):
        if not env.exists():
            continue
        for line in env.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = line.strip()
            if line.startswith("export "):
                line = line[7:]
            k, sep, v = line.partition("=")
            if sep and k.strip() in need and not os.environ.get(k.strip()):
                os.environ[k.strip()] = v.strip().strip('"').strip("'")
        return


def queue_client() -> Any:
    load_env()
    url = (os.environ.get("JARVIS_SUPABASE_URL") or "").strip()
    key = (os.environ.get("JARVIS_SUPABASE_SERVICE_ROLE_KEY") or "").strip()
    if not url or not key:
        raise SystemExit("JARVIS_SUPABASE_* 未設定")
    from supabase import create_client

    return create_client(url, key)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def queue_list() -> int:
    sb = queue_client()
    rows = (
        sb.table(QUEUE_TABLE)
        .select("id, agent_id, status, created_at, finished_at")
        .order("created_at", desc=True)
        .limit(10)
        .execute()
        .data
        or []
    )
    for r in rows:
        print(r["created_at"][:19], r["agent_id"], r["status"], r["id"])
    if not rows:
        print("待ち箱は空です")
    return 0


def queue_once() -> int:
    sb = queue_client()
    rows = (
        sb.table(QUEUE_TABLE).select("*").eq("status", "queued").order("created_at").limit(1).execute().data
        or []
    )
    if not rows:
        print("待ち箱は空です")
        return 0
    row = rows[0]
    got = (
        sb.table(QUEUE_TABLE)
        .update({"status": "running", "started_at": now_iso()})
        .eq("id", row["id"])
        .eq("status", "queued")
        .execute()
        .data
    )
    if not got:
        print("他の実行が先に拾いました")
        return 0
    print(f"拾いました: {row['id']} agent={row['agent_id']}")

    def finish(status: str, **cols: Any) -> None:
        sb.table(QUEUE_TABLE).update({"status": status, "finished_at": now_iso(), **cols}).eq(
            "id", row["id"]
        ).execute()

    try:
        # registry の今の ID を正とする（待ち箱に入った後で付け替わっていても古い方へ送らない）
        fid = flow_id_for_agent(str(row["agent_id"]))
        text = str(row["instructions"]).strip()
        if str(row.get("kind") or "edit") != "undo" and (not text or len(text) > MAX_CHARS):
            raise PasteStop(7, "修正文が空か長すぎます")
        if str(row.get("kind") or "edit") == "undo":
            ref = (
                sb.table(QUEUE_TABLE).select("result, status, flow_id").eq("id", row.get("ref_id")).limit(1).execute().data
                or []
            )
            if not ref or ref[0].get("status") != "sent" or not ref[0].get("result"):
                raise PasteStop(7, "取り消す対象の送信記録が見つかりません")
            if ref[0].get("flow_id") != fid:
                raise PasteStop(7, "取り消す対象のフローが今の登録と違います")
            target = json.loads(ref[0]["result"]).get("updatedAt_before")
            if not target:
                raise PasteStop(7, "送信前の更新日時が記録にありません")
            tab, _ = prepare(fid)
            result = undo_to(tab, fid, target, None)
        else:
            tab, owns = prepare(fid)
            fill(tab, text)
            result = send_and_wait(tab, fid, owns)
    except PasteStop as e:
        print(str(e))
        finish("error", error=str(e)[:500])
        return e.code
    except Exception as e:  # osascript の失敗など
        print("失敗:", e)
        finish("error", error=str(e)[:500])
        return 1
    print("結果:", {k: v for k, v in result.items() if k != "reply"})
    finish("sent", result=json.dumps(result, ensure_ascii=False)[:4000])
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="FlowForge AIアシスタントへ修正文を入力（試作）")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--agent", help="社員番号（例: 311）")
    g.add_argument("--flow-id", help="flow_… を直接指定")
    g.add_argument("--queue-once", action="store_true", help="待ち箱から1件拾って送信し、結果を書き戻す")
    g.add_argument("--queue-list", action="store_true", help="待ち箱の直近10件を表示")
    ap.add_argument("--text-file", help="修正文のファイル（UTF-8）")
    ap.add_argument("--check", action="store_true", help="持ち主かどうかと画面の状態だけ確かめる")
    ap.add_argument("--send", action="store_true", help="入力後に送信まで行う（既定は入力だけ）")
    ap.add_argument("--undo", type=int, metavar="N", help="「元に戻す」を N 回押す（1〜6）")
    args = ap.parse_args()

    if args.queue_list:
        return queue_list()
    if args.queue_once:
        return queue_once()

    fid = args.flow_id or flow_id_for_agent(args.agent)
    text = ""
    if args.undo:
        if not 1 <= args.undo <= UNDO_MAX_PRESSES:
            ap.error(f"--undo は 1〜{UNDO_MAX_PRESSES}")
        try:
            tab, _ = prepare(fid)
            result = undo_to(tab, fid, None, args.undo)
        except PasteStop as e:
            print(str(e))
            return e.code
        print("結果:", result)
        return 0
    if not args.check:
        if not args.text_file:
            ap.error("--text-file が必要です（確認だけなら --check）")
        text = Path(args.text_file).read_text(encoding="utf-8").strip()
        if not text:
            raise SystemExit("修正文が空です")
        if len(text) > MAX_CHARS:
            raise SystemExit(f"修正文が長すぎます（{len(text)} 文字）。小分けにしてください")

    try:
        tab, owns = prepare(fid)
        if args.check:
            return 0
        fill(tab, text)
        if not args.send:
            print("送信はしていません（--send なし）。画面で文を確かめてください。")
            return 0
        result = send_and_wait(tab, fid, owns)
    except PasteStop as e:
        print(str(e))
        return e.code
    print("結果:", {k: v for k, v in result.items() if k != "reply"})
    print("AIアシスタントの返事:\n" + result["reply"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
