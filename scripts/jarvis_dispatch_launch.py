#!/usr/bin/env python3
"""611×317 配車案の ✅ 起動 — #consult の配車案への了承を拾い、了承された番号だけ担当ツールを起動する。

流れ:
  1. 611 が配車案を #consult に出す（jarvis_ai_dispatch_suggest.py --post）。投稿に「配車ID」を入れ、
     中身を .jarvis_state/dispatch_queue/<配車ID>.json に残す
  2. 317 コメント起動（jarvis_comment_dispatch.py）の巡回で、このスクリプトを呼ぶ
  3. 松野さんの ✅ リアクション（全件）か、スレッド返信（「1と3OK、2はCodexで」）を読む
  4. 了承された番号だけ起動する
       Codex       … Mac の `codex exec`（作業ブランチの worktree で）
       Claude Code … Mac の `claude -p`（同上）
       Cursor      … CURSOR_API_KEY の Cloud Agent
       チャッピー・フライデー … 自動不可。そのまま貼れる依頼文をスレッドに返す
  5. 成果はドラフト PR で止める。PR が出たらリンクを同じスレッドに返す。マージは人

安全:
  - お金・対外送信・本番変更・削除を含む行は ✅ でも起動しない（「了承待ち」と返す）
  - 現担当のまま／固定の行は起動しない
  - 同時起動の上限（JARVIS_DISPATCH_LAUNCH_MAX、既定 2）、処理済みの記録で二重起動しない
  - 停止: JARVIS_DISPATCH_LAUNCH_DISABLE=1。夜間は 317 と同じ時間帯は動かない
  - 本当に起動するのは --apply かつ JARVIS_DISPATCH_LAUNCH_ENABLE=1 のときだけ。
    それ以外は「何を起動するか」を出すだけ（dry-run）
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

JST = ZoneInfo("Asia/Tokyo")
REPO = Path(__file__).resolve().parents[1]
SCRIPTS = REPO / "scripts"
QUEUE_DIR = REPO / ".jarvis_state" / "dispatch_queue"
STATE_PATH = REPO / ".jarvis_state" / "dispatch_launch.json"
WORKTREES = REPO / ".jarvis_state" / "dispatch_worktrees"
CONSULT_CHANNEL = os.environ.get("JARVIS_SLACK_CONSULT_CHANNEL", "C0C7R0UF3MM")
OWNER_USER = os.environ.get("JARVIS_OWNER_SLACK_USER", "U0C7X79N4P7")
APPROVE_REACTIONS = {"white_check_mark", "heavy_check_mark", "ballot_box_with_check", "o", "ok"}
RISK_WORDS = ("送金", "振込", "銀行", "OTP", "対外送信", "返信", "送信", "投稿", "本番", "削除",
              "migration", "マイグレーション", "デプロイ", "課金")
AUTO_AGENTS = {"codex", "claude_code", "cursor"}
AGENT_WORDS = {
    "codex": ("codex", "コーデックス"),
    "claude_code": ("claude", "クロード", "ミスレモン", "miss lemon"),
    "cursor": ("cursor", "カーソル", "ジャービス", "jarvis"),
    "chatgpt_mode": ("chatgpt", "チャッピー"),
    "gencode": ("gencode", "フライデー", "friday"),
}
AGENT_NAME = {"codex": "Codex", "claude_code": "ミスレモン", "cursor": "ジャービス",
              "chatgpt_mode": "チャッピー", "gencode": "フライデー"}
RUN_TIMEOUT_H = 6


# ------------------------------------------------------------------ 設定
def _flag(name: str, default: str = "") -> bool:
    return (os.environ.get(name) or default).strip().lower() in ("1", "true", "yes", "on")


def max_concurrent() -> int:
    try:
        return max(1, int(os.environ.get("JARVIS_DISPATCH_LAUNCH_MAX") or "2"))
    except ValueError:
        return 2


def in_quiet_hours() -> bool:
    try:
        sys.path.insert(0, str(SCRIPTS))
        import jarvis_comment_dispatch as cd  # 317 と同じ夜間帯
        return bool(cd.in_quiet_hours())
    except Exception:
        return False


def load_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def save_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


# ------------------------------------------------------------------ 了承の読み取り
_Z2H = str.maketrans("０１２３４５６７８９", "0123456789")


def parse_approval(texts: list[str], n_items: int) -> dict[int, dict[str, Any]]:
    """松野さんの返信から {番号: {"ok": bool, "agent": 上書き or None}} を作る。後の返信が優先。"""
    out: dict[int, dict[str, Any]] = {}
    for text in texts:
        t = (text or "").translate(_Z2H)
        for clause in re.split(r"[、,。\n;；]", t):
            c = clause.strip()
            if not c:
                continue
            low = c.lower()
            nums = [int(x) for x in re.findall(r"\d+", c) if 1 <= int(x) <= n_items]
            if not nums and re.search(r"全部|すべて|全て|ぜんぶ", c):
                nums = list(range(1, n_items + 1))
            if not nums:
                continue
            agent = None
            for k, words in AGENT_WORDS.items():
                if any(w in low for w in words):
                    agent = k
            if re.search(r"なし|不要|やめ|ng|待って|保留|見送", low):
                for n in nums:
                    out[n] = {"ok": False, "agent": None}
            elif agent or re.search(r"ok|了承|お願い|やって|go|進めて|いい", low):
                for n in nums:
                    out[n] = {"ok": True, "agent": agent}
    return out


def approvals_from(reactions: list[dict[str, Any]], replies: list[dict[str, Any]],
                   n_items: int) -> dict[int, dict[str, Any]]:
    res: dict[int, dict[str, Any]] = {}
    for r in reactions:
        name = (r.get("name") or "").split("::", 1)[0]
        if name in APPROVE_REACTIONS and OWNER_USER in (r.get("users") or []):
            res = {n: {"ok": True, "agent": None} for n in range(1, n_items + 1)}
    texts = [m.get("text") or "" for m in replies if m.get("user") == OWNER_USER]
    res.update(parse_approval(texts, n_items))
    return res


# ------------------------------------------------------------------ 計画
def is_risky(item: dict[str, Any]) -> bool:
    blob = " ".join([item.get("title") or "", item.get("request") or "", " ".join(item.get("notes") or []),
                     item.get("kind") or ""])
    return item.get("kind") == "money" or any(w in blob for w in RISK_WORDS)


def plan(record: dict[str, Any], approvals: dict[int, dict[str, Any]], state: dict[str, Any],
         running: int) -> list[dict[str, Any]]:
    """了承済みの各番号について、何をするか（launch / reply / skip）を決める。副作用なし。"""
    done = state.get("handled") or {}
    actions: list[dict[str, Any]] = []
    slots = max(0, max_concurrent() - running)
    for it in record.get("items") or []:
        n = int(it["no"])
        key = f"{record['id']}#{n}"
        ap = approvals.get(n)
        if not ap or key in done:
            continue
        if not ap["ok"]:
            actions.append({"no": n, "key": key, "do": "skip", "why": "見送り（松野さん）"})
            continue
        agent = ap.get("agent") or it.get("agent")
        base = {"no": n, "key": key, "agent": agent, "item": it}
        if it.get("mode") == "keep":
            actions.append({**base, "do": "skip", "why": "現担当のまま。起動しない"})
        elif it.get("mode") == "fixed" and not ap.get("agent"):
            actions.append({**base, "do": "skip", "why": "固定（定期で動く）。二重に動かさないため起動しない"})
        elif is_risky(it):
            actions.append({**base, "do": "reply", "why": "お金・対外送信・本番・削除を含むので自動起動しない。了承待ち",
                            "text": it.get("request_text") or ""})
        elif agent not in AUTO_AGENTS:
            actions.append({**base, "do": "reply", "why": f"{AGENT_NAME.get(agent, agent)}は自動起動できない。下の依頼文を貼ってください",
                            "text": it.get("request_text") or ""})
        elif slots <= 0:
            actions.append({**base, "do": "wait", "why": f"同時起動の上限 {max_concurrent()} 件。次の巡回で起動"})
        else:
            slots -= 1
            actions.append({**base, "do": "launch", "why": f"{AGENT_NAME.get(agent, agent)}を起動（ドラフト PR で止める）"})
    return actions


def branch_name(key: str) -> str:
    return "dispatch/" + re.sub(r"[^A-Za-z0-9_-]+", "-", key).strip("-")


def agent_prompt(it: dict[str, Any], branch: str) -> str:
    return (
        f"611 配車（松野さん了承済み）: {it.get('title')}\n"
        f"渡し票: {it.get('path') or '（無し。必要なら作る）'}\n"
        f"作業ブランチ {branch} の上だけで作業する。渡し票の完了条件まで進め、検証結果を TASK.md に書く。\n"
        "終わったら commit → `git push -u origin " + branch + "` → `gh pr create --draft` でドラフト PR を作り、URL を最後に出力する。\n"
        "禁止: main への push、マージ、送金・対外送信・本番変更・削除、秘密の値の出力。迷ったら止めて PR 本文に書く。"
    )


def launch_cmd(agent: str, workdir: Path, prompt: str) -> list[str]:
    if agent == "codex":
        return ["codex", "exec", "--cd", str(workdir), "--full-auto", prompt]
    extra = (os.environ.get("JARVIS_DISPATCH_CLAUDE_ARGS")
             or "--permission-mode acceptEdits --allowedTools Bash(git:*),Bash(gh pr create:*),Bash(python3:*)").split()
    return ["claude", "-p", prompt, *extra]


# ------------------------------------------------------------------ 実行（副作用）
def _slack(method: str, params: dict[str, str], post: bool = False) -> dict[str, Any]:
    token = (os.environ.get("SLACK_BOT_TOKEN") or os.environ.get("SLACK_USER_TOKEN") or "").strip()
    if not token:
        raise RuntimeError("slack token 未設定")
    url = f"https://slack.com/api/{method}"
    if post:
        req = urllib.request.Request(url, data=json.dumps(params).encode(), method="POST",
                                     headers={"Authorization": f"Bearer {token}",
                                              "Content-Type": "application/json; charset=utf-8"})
    else:
        req = urllib.request.Request(url + "?" + urllib.parse.urlencode(params),
                                     headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.loads(r.read().decode("utf-8"))
    if not data.get("ok"):
        raise RuntimeError(data.get("error") or method)
    return data


def find_post_ts(record: dict[str, Any]) -> str | None:
    if record.get("ts"):
        return record["ts"]
    data = _slack("conversations.history", {"channel": CONSULT_CHANNEL, "limit": "100"})
    for m in data.get("messages") or []:
        if f"配車ID: {record['id']}" in (m.get("text") or ""):
            return m.get("ts")
    return None


def read_feedback(ts: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    msg = (_slack("reactions.get", {"channel": CONSULT_CHANNEL, "timestamp": ts, "full": "true"})
           .get("message") or {})
    reps = _slack("conversations.replies", {"channel": CONSULT_CHANNEL, "ts": ts, "limit": "100"}).get("messages") or []
    return list(msg.get("reactions") or []), reps[1:]


def reply(ts: str, text: str, *, dry: bool) -> None:
    if dry:
        print(f"[dry-run] スレッド返信: {text.splitlines()[0][:80]}")
        return
    try:
        _slack("chat.postMessage", {"channel": CONSULT_CHANNEL, "thread_ts": ts, "text": text}, post=True)
    except Exception as e:  # スレッド返信できなければ #consult に配車ID付きで出す
        subprocess.run([sys.executable, str(SCRIPTS / "jarvis_slack_webhook_post.py"), "--channel", "consult",
                        "--username", "611 配車係", "--text", text], check=False)
        print(f"# thread reply fallback: {type(e).__name__}", file=sys.stderr)


def start_job(agent: str, key: str, it: dict[str, Any]) -> dict[str, Any]:
    branch = branch_name(key)
    prompt = agent_prompt(it, branch)
    if agent == "cursor":
        sys.path.insert(0, str(SCRIPTS))
        from jarvis_cloud_agent_launch import launch_cloud_agent
        res = launch_cloud_agent(prompt=prompt, name=f"611-{key}", auto_create_pr=True)
        return {"agent": agent, "branch": branch, "status": "running" if res.get("ok") else "failed",
                "url": res.get("url"), "error": res.get("error")}
    wt = WORKTREES / branch.replace("/", "_")
    subprocess.run(["git", "fetch", "-q", "origin", "main"], cwd=REPO, check=True)
    subprocess.run(["git", "worktree", "add", "-q", "-b", branch, str(wt), "origin/main"], cwd=REPO, check=True)
    log = open(wt.with_suffix(".log"), "w")
    p = subprocess.Popen(launch_cmd(agent, wt, prompt), cwd=wt, stdout=log, stderr=subprocess.STDOUT,
                         start_new_session=True)
    return {"agent": agent, "branch": branch, "status": "running", "pid": p.pid, "worktree": str(wt)}


def pr_url(branch: str) -> str | None:
    r = subprocess.run(["gh", "pr", "list", "--head", branch, "--state", "all", "--json", "url", "-q", ".[0].url"],
                       cwd=REPO, capture_output=True, text=True)
    return (r.stdout or "").strip() or None


def count_running(state: dict[str, Any], now: datetime) -> int:
    n = 0
    for job in (state.get("jobs") or {}).values():
        if job.get("status") != "running":
            continue
        try:
            started = datetime.fromisoformat(job["started_at"])
        except (KeyError, ValueError):
            continue
        if now - started < timedelta(hours=RUN_TIMEOUT_H):
            n += 1
    return n


def follow_up(state: dict[str, Any], *, dry: bool) -> None:
    """起動中のジョブの PR が出ていたら、同じスレッドにリンクを返す。"""
    for key, job in (state.get("jobs") or {}).items():
        if job.get("status") != "running" or job.get("agent") == "cursor":
            continue
        url = pr_url(job["branch"])
        if url:
            reply(job["thread_ts"], f"{key.split('#')[-1]}. ドラフト PR ができました: {url}（マージは松野さん）", dry=dry)
            if not dry:
                job["status"] = "pr_opened"
                job["pr"] = url


def run(*, apply: bool) -> int:
    real = apply and _flag("JARVIS_DISPATCH_LAUNCH_ENABLE")
    dry = not real
    if _flag("JARVIS_DISPATCH_LAUNCH_DISABLE"):
        print("611 dispatch: disabled")
        return 0
    if in_quiet_hours():
        print("611 dispatch: quiet hours — skip")
        return 0
    state = load_json(STATE_PATH, {})
    now = datetime.now(JST)
    follow_up(state, dry=dry)
    running = count_running(state, now)
    for qf in sorted(QUEUE_DIR.glob("*.json")):
        rec = load_json(qf, {})
        if not rec.get("items") or rec.get("closed"):
            continue
        try:
            ts = find_post_ts(rec)
            if not ts:
                continue
            reactions, replies = read_feedback(ts)
        except Exception as e:
            print(f"# slack read skip {rec.get('id')}: {type(e).__name__}", file=sys.stderr)
            continue
        acts = plan(rec, approvals_from(reactions, replies, len(rec["items"])), state, running)
        for a in acts:
            head = f"{a['no']}. {a['item']['title'] if a.get('item') else ''}"
            print(f"{'[dry-run] ' if dry else ''}{a['do']}: {head} — {a['why']}")
            if a["do"] == "wait":
                continue
            if a["do"] == "launch":
                if dry:
                    print(f"[dry-run] 起動する: {a['agent']} ブランチ {branch_name(a['key'])}")
                    continue
                try:
                    job = start_job(a["agent"], a["key"], a["item"])
                except Exception as e:
                    job = {"agent": a["agent"], "status": "failed", "error": type(e).__name__}
                job.update({"started_at": now.isoformat(), "thread_ts": ts})
                state.setdefault("jobs", {})[a["key"]] = job
                running += 1
                msg = f"{a['no']}. {AGENT_NAME.get(a['agent'])}を起動しました（ブランチ {job.get('branch')}）。PR が出たらここに貼ります"
                if job["status"] == "failed":
                    msg = f"{a['no']}. 起動に失敗しました（{job.get('error')}）。依頼文を手で貼ってください"
                reply(ts, msg, dry=False)
            elif a["do"] == "reply":
                reply(ts, f"{a['no']}. {a['why']}\n{a.get('text') or ''}".strip(), dry=dry)
            if not dry:
                state.setdefault("handled", {})[a["key"]] = {"at": now.isoformat(), "do": a["do"]}
    if not dry:
        save_json(STATE_PATH, state)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="611 配車案の ✅ 起動（317 から呼ぶ）")
    ap.add_argument("--apply", action="store_true", help="JARVIS_DISPATCH_LAUNCH_ENABLE=1 のときだけ本当に起動")
    ap.add_argument("--dry-run", action="store_true", help="何を起動するかだけ出す（既定）")
    args = ap.parse_args()
    try:
        return run(apply=args.apply and not args.dry_run)
    except Exception as e:  # 317 を止めない
        print(f"# 611 dispatch skip: {type(e).__name__}", file=sys.stderr)
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
