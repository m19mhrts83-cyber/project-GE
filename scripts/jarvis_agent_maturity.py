#!/usr/bin/env python3
"""AIエージェント運用成熟度: 週1回の計測（チーム全体＋判断ログに社員番号がある社員）。

物差しは apps/jarvis-dashboard/config/agent_maturity.json。ここでは実測値だけを集めて
Supabase agent_maturity_snapshots に 1 行ずつ足す（同じ日・同じ範囲は二重に入れない）。
取れない指標は値を入れず、理由を metrics._missing に残す（推測で埋めない）。

  python scripts/jarvis_agent_maturity.py --dry-run   # 集計結果を表示するだけ
  python scripts/jarvis_agent_maturity.py             # 記録する

環境変数: JARVIS_SUPABASE_URL, JARVIS_SUPABASE_SERVICE_ROLE_KEY,
          GITHUB_TOKEN（任意。無いと保守性の指標は未計測）, GITHUB_REPOSITORY（既定 m19mhrts83-cyber/project-GE）
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

JST = timezone(timedelta(hours=9))
ROOT = Path(__file__).resolve().parent.parent
DASH = ROOT / "apps" / "jarvis-dashboard"
WINDOW_DAYS = 28
AI_MARKS = ("🤖", "🦾依頼")
SIGNER_RE = re.compile(r"^【([^】・\s]+)")
FIX_RE = re.compile(r"^(fix|hotfix|revert)\b|修正|不具合|直す|直し", re.IGNORECASE)


# ---------- 入出力 ----------

def _env() -> tuple[str, str]:
    url = os.environ.get("JARVIS_SUPABASE_URL", "").rstrip("/")
    key = os.environ.get("JARVIS_SUPABASE_SERVICE_ROLE_KEY", "")
    if not url or not key:
        print("JARVIS_SUPABASE_URL / JARVIS_SUPABASE_SERVICE_ROLE_KEY が未設定", file=sys.stderr)
        sys.exit(2)
    return url, key


def rest(path: str, params: dict | None = None, method: str = "GET", body=None, prefer: str = "return=minimal"):
    url, key = _env()
    q = ("?" + urllib.parse.urlencode(params, safe=",.:()*")) if params else ""
    req = urllib.request.Request(
        f"{url}/rest/v1/{path}{q}",
        method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "Prefer": prefer,
        },
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        raw = r.read()
    return json.loads(raw) if raw else None


def gh(path: str, params: dict | None = None):
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if not token:
        return None
    q = ("?" + urllib.parse.urlencode(params)) if params else ""
    req = urllib.request.Request(
        f"https://api.github.com{path}{q}",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())


def iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_ts(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except ValueError:
        return None


def ratio(num: int, den: int, min_n: int, key: str, missing: dict, why: str) -> dict | None:
    if den < max(1, min_n):
        missing[key] = f"{why}（母数 {den} 件。{min_n} 件以上で計測）"
        return None
    return {"value": round(num / den, 4), "num": num, "den": den}


# ---------- 指標 ----------

def m_agents(out: dict, missing: dict) -> None:
    data = json.loads((DASH / "data" / "agentTeam.json").read_text(encoding="utf-8"))
    agents = [a for a in data.get("agents", []) if "廃止" not in str(a.get("status", ""))]
    active = [
        a for a in agents
        if a.get("status") in ("運用確認", "運用") and not str(a.get("trigger", "")).strip() in ("", "人依頼")
    ]
    out["active_agent_ratio"] = {"value": round(len(active) / len(agents), 4), "num": len(active), "den": len(agents)}
    out["operating_agents"] = {"value": sum(1 for a in agents if a.get("status") == "運用")}


def m_decisions(rows: list[dict], out: dict, missing: dict, meta: dict) -> None:
    good = sum(1 for r in rows if r.get("surface") == "triage_miss" and r.get("action") == "good")
    wrong = sum(1 for r in rows if r.get("surface") == "triage_miss" and r.get("action") == "wrong")
    v = ratio(good, good + wrong, meta["triage_hit_rate"].get("min_n", 1), "triage_hit_rate", missing, "仕分けの当否の記録が少ない")
    if v:
        out["triage_hit_rate"] = v

    out["rules_adopted_28d"] = {
        "value": sum(1 for r in rows if r.get("surface") == "rule_review" and r.get("action") == "rule_accept")
    }

    edited = [r for r in rows if r.get("edited") is not None]
    v = ratio(
        sum(1 for r in edited if r.get("edited") is False),
        len(edited),
        meta["draft_no_edit_rate"].get("min_n", 1),
        "draft_no_edit_rate",
        missing,
        "「下書きを直したか」の記入が少ない",
    )
    if v:
        out["draft_no_edit_rate"] = v


def m_sent(rows: list[dict], now: datetime, out: dict) -> None:
    since = now - timedelta(days=7)
    out["sent_per_week"] = {
        "value": sum(
            1 for r in rows
            if r.get("surface") == "triage" and r.get("action") == "sent" and (parse_ts(r.get("decided_at")) or now) >= since
        )
    }


def m_todoist(events: list[dict], out: dict, missing: dict, meta: dict) -> None:
    added_ai: set[str] = set()
    completed: set[str] = set()
    signers: dict[str, set[str]] = defaultdict(set)
    for e in events:
        d = e.get("event_data") or {}
        name = e.get("event_name")
        if name == "item:added" and str(d.get("content", "")).startswith(AI_MARKS):
            added_ai.add(str(d.get("id")))
        elif name == "item:completed":
            completed.add(str(d.get("id")))
        elif name == "note:added":
            m = SIGNER_RE.match(str(d.get("content", "")).strip())
            if m and d.get("item_id"):
                signers[str(d["item_id"])].add(m.group(1))
    v = ratio(
        len(added_ai & completed), len(added_ai),
        meta["ai_task_completion"].get("min_n", 1), "ai_task_completion", missing,
        "🤖・🦾依頼の印つきで起票されたタスクが少ない",
    )
    if v:
        out["ai_task_completion"] = v
    handed = {i for i, s in signers.items() if len(s) >= 2}
    v = ratio(
        len(handed & completed), len(handed),
        meta["handoff_completion"].get("min_n", 1), "handoff_completion", missing,
        "署名が2種類以上あるタスクが少ない",
    )
    if v:
        v["note"] = "署名（【Claude】【Jarvis】など）の交代で数えた近似"
        out["handoff_completion"] = v


def m_jobs(rows: list[dict], out: dict, missing: dict, meta: dict) -> None:
    ok = sum(1 for r in rows if r.get("status") == "succeeded")
    ng = sum(1 for r in rows if r.get("status") == "failed")
    v = ratio(ok, ok + ng, meta["job_success_rate"].get("min_n", 1), "job_success_rate", missing, "ジョブの実行が少ない")
    if v:
        out["job_success_rate"] = v


def m_stability(cfg: dict, now: datetime, out: dict) -> None:
    att = rest("watch_status", {"select": "id", "status": "eq.active", "level": "eq.attention"}) or []
    out["watch_attention"] = {"value": len(att)}
    keys = cfg.get("heartbeats", {})
    rows = rest("sync_meta", {"select": "key,updated_at", "key": f"in.({','.join(keys)})"}) or []
    seen = {r["key"]: parse_ts(r.get("updated_at")) for r in rows}
    stale = [k for k, days in keys.items() if not seen.get(k) or now - seen[k] > timedelta(days=days)]
    out["stale_heartbeats"] = {"value": len(stale), "note": "、".join(stale) if stale else ""}


def m_uiux(out: dict, missing: dict) -> None:
    p = DASH / "config" / "uiux_scorecard.json"
    if not p.exists():
        missing["uiux_japan_avg"] = "UI/UX採点表が見つからない"
        return
    sc = json.loads(p.read_text(encoding="utf-8"))
    evals = sorted(sc.get("evaluations", []), key=lambda e: e.get("date", ""))
    if not evals:
        missing["uiux_japan_avg"] = "UI/UX採点がまだ無い"
        return
    axes = [a["key"] for a in sc.get("axes", [])]
    totals = []
    for app in sc.get("apps", []):
        s = evals[-1].get("scores", {}).get(app["key"], {}).get("japan", {})
        vals = [s[a] for a in axes if isinstance(s.get(a), (int, float))]
        if vals:
            totals.append(round(sum(vals) / (len(vals) * 10) * 100))
    if totals:
        out["uiux_japan_avg"] = {"value": round(sum(totals) / len(totals), 1), "note": f"{evals[-1].get('date')} 採点"}


def m_github(since: datetime, out: dict, missing: dict, meta: dict) -> None:
    repo = os.environ.get("GITHUB_REPOSITORY", "m19mhrts83-cyber/project-GE")
    if not os.environ.get("GITHUB_TOKEN", "").strip():
        missing["fix_pr_ratio"] = missing["ci_pass_rate"] = "GITHUB_TOKEN が無い"
        return
    day = since.strftime("%Y-%m-%d")
    titles: list[str] = []
    try:
        for page in range(1, 11):
            res = gh("/search/issues", {"q": f"repo:{repo} is:pr is:merged merged:>={day}", "per_page": 100, "page": page})
            items = (res or {}).get("items", [])
            titles += [str(i.get("title", "")) for i in items]
            if len(items) < 100:
                break
        v = ratio(sum(1 for t in titles if FIX_RE.search(t)), len(titles), meta["fix_pr_ratio"].get("min_n", 1),
                  "fix_pr_ratio", missing, "マージしたPRが少ない")
        if v:
            v["note"] = "件名（fix・修正・不具合など）で判定した近似"
            out["fix_pr_ratio"] = v
    except urllib.error.URLError as e:
        missing["fix_pr_ratio"] = f"GitHub検索に失敗（{e}）"
    try:
        ok = ng = 0
        for page in range(1, 11):
            res = gh(f"/repos/{repo}/actions/workflows/pr-checks.yml/runs",
                     {"created": f">={day}", "per_page": 100, "page": page, "status": "completed"})
            runs = (res or {}).get("workflow_runs", [])
            ok += sum(1 for r in runs if r.get("conclusion") == "success")
            ng += sum(1 for r in runs if r.get("conclusion") == "failure")
            if len(runs) < 100:
                break
        v = ratio(ok, ok + ng, meta["ci_pass_rate"].get("min_n", 1), "ci_pass_rate", missing, "CIの実行が少ない")
        if v:
            out["ci_pass_rate"] = v
    except urllib.error.URLError as e:
        missing["ci_pass_rate"] = f"GitHub Actionsの取得に失敗（{e}）"


def m_cost(cfg: dict, out: dict, missing: dict, events: list[dict], now: datetime) -> None:
    if not cfg.get("cost_ledger_complete"):
        missing["ai_cost_per_done"] = "サブスク台帳にClaude・Grokの月額がまだ無い"
        return
    subs = rest("subscription_services", {"select": "monthly_yen,status", "category": "eq.ai", "status": "eq.active"}) or []
    yen = sum(float(s.get("monthly_yen") or 0) for s in subs)
    since = now - timedelta(days=30)
    done = {
        str((e.get("event_data") or {}).get("id"))
        for e in events
        if e.get("event_name") == "item:completed" and (parse_ts(e.get("created_at")) or now) >= since
    }
    if not done or not yen:
        missing["ai_cost_per_done"] = "月額または完了タスクが0件"
        return
    out["ai_cost_per_done"] = {"value": round(yen / len(done)), "num": round(yen), "den": len(done)}


def per_employee(rows: list[dict]) -> dict[str, dict]:
    by: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        emp = str(r.get("employee") or "").strip()
        if re.fullmatch(r"\d{3}", emp):
            by[emp].append(r)
    res: dict[str, dict] = {}
    for emp, rs in by.items():
        if len(rs) < 5:
            continue
        outcomes = [str((r.get("payload") or {}).get("outcome") or "") for r in rs]
        take, ng = outcomes.count("take"), outcomes.count("ng")
        m: dict = {"decisions_28d": {"value": len(rs)}}
        if take + ng >= 5:
            m["take_rate"] = {"value": round(take / (take + ng), 4), "num": take, "den": take + ng}
        res[emp] = m
    return res


# ---------- 本体 ----------

def collect(now: datetime) -> tuple[dict, dict[str, dict]]:
    cfg = json.loads((DASH / "config" / "agent_maturity.json").read_text(encoding="utf-8"))
    meta = cfg["metrics"]
    since = now - timedelta(days=WINDOW_DAYS)
    out: dict = {}
    missing: dict = {}

    decisions = rest("owner_decisions", {
        "select": "surface,action,employee,edited,payload,decided_at",
        "decided_at": f"gte.{iso(since)}", "limit": "10000",
    }) or []
    events = rest("todoist_webhook_events", {
        "select": "event_name,event_data,created_at",
        "created_at": f"gte.{iso(since)}",
        "event_name": "in.(item:added,item:completed,note:added)", "limit": "20000",
    }) or []
    jobs = rest("kurashift_jobs", {"select": "status", "created_at": f"gte.{iso(since)}", "limit": "5000"}) or []

    m_agents(out, missing)
    m_decisions(decisions, out, missing, meta)
    m_sent(decisions, now, out)
    m_todoist(events, out, missing, meta)
    m_jobs(jobs, out, missing, meta)
    m_stability(cfg, now, out)
    m_uiux(out, missing)
    m_github(since, out, missing, meta)
    m_cost(cfg, out, missing, events, now)
    out["_missing"] = missing
    out["_window_days"] = WINDOW_DAYS
    return out, per_employee(decisions)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    now = datetime.now(timezone.utc)
    day = now.astimezone(JST).strftime("%Y-%m-%d")
    team, emps = collect(now)
    rows = [{"measured_on": day, "scope": "team", "metrics": team, "method": "auto"}]
    rows += [{"measured_on": day, "scope": e, "metrics": m, "method": "auto"} for e, m in sorted(emps.items())]
    print(json.dumps(rows, ensure_ascii=False, indent=2))
    if args.dry_run:
        return 0
    rest(
        "agent_maturity_snapshots",
        {"on_conflict": "measured_on,scope"},
        method="POST",
        body=rows,
        prefer="return=minimal,resolution=ignore-duplicates",
    )
    print(f"recorded {len(rows)} rows for {day}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
