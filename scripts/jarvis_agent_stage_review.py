#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""AI社員の段階（設計中 → 運用確認 → 運用）を週次レビューで見直す（AI なし）。

土曜 9:00（314 週次に相乗り）: 週次稼働（scripts/jarvis_agent_weekly_activity.py の metrics 履歴）と
松野さんの判断ログ（owner_decisions）から「上げる／戻す提案」を作り、sync_meta(agent_stage_review) に置く。
→ 松野さんが /review「AI社員の段階」で 上げる／見送る／来週また を押し、理由を書く（owner_decisions surface=agent_stage）。
→ 採用した分だけ、9:30 の 314 点検が --apply --commit で agents_registry.yaml の status を直し、
   jarvis_agent_team_status_sync.py（マーカー・状態ボード・README・ダッシュ JSON）を流す。

状態は勝手に変えない（22_運用状態の識別「状態変更は提案が先」）。ここは提案と、了承済みの反映だけ。
物差し: config/agent_stage_review.yaml

  python scripts/jarvis_agent_stage_review.py --dry-run     # 提案を表示
  python scripts/jarvis_agent_stage_review.py --push        # sync_meta に置く（土曜 runner）
  python scripts/jarvis_agent_stage_review.py --apply --dry-run
  python scripts/jarvis_agent_stage_review.py --apply --commit   # 採用分を registry に反映して1件1コミット
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
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from jarvis_owner_decision_log import outcome_of  # noqa: E402

JST = timezone(timedelta(hours=9))
REPO = Path(__file__).resolve().parents[1]
CONFIG = REPO / "config" / "agent_stage_review.yaml"
REGISTRY = REPO / "docs" / "AIエージェントチーム" / "agents_registry.yaml"
ACTIVITY_LATEST = REPO / ".jarvis_state" / "agent_weekly_activity" / "latest.json"
STATE_DIR = REPO / ".jarvis_state" / "agent_stage_review"
REVIEW_URL = "https://jarvis-dashboard-amber.vercel.app/review#stage"
SURFACE = "agent_stage"
STAGES = ("設計中", "運用確認", "運用")
LOG = "agent_stage_review"


# ---------- 入出力 ----------

def rest(path: str, params: dict | None = None, method: str = "GET", body: Any = None) -> Any:
    url = (os.environ.get("JARVIS_SUPABASE_URL") or "").rstrip("/")
    key = os.environ.get("JARVIS_SUPABASE_SERVICE_ROLE_KEY") or ""
    if not url or not key:
        raise RuntimeError("JARVIS_SUPABASE_URL / JARVIS_SUPABASE_SERVICE_ROLE_KEY が未設定")
    q = ("?" + urllib.parse.urlencode(params, safe=",.:()*>")) if params else ""
    req = urllib.request.Request(
        f"{url}/rest/v1/{path}{q}", method=method,
        data=json.dumps(body, ensure_ascii=False).encode() if body is not None else None,
        headers={"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json",
                 "Prefer": "return=minimal,resolution=merge-duplicates"},
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        raw = r.read()
    return json.loads(raw) if raw else None


def load_cfg(path: Path = CONFIG) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def load_agents(path: Path = REGISTRY) -> list[dict[str, str]]:
    reg = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    out = []
    for aid, a in (reg.get("agents") or {}).items():
        st = str((a or {}).get("status") or "")
        if st in STAGES:
            out.append({"id": str(aid), "name": str(a.get("name") or ""), "status": st})
    return sorted(out, key=lambda x: x["id"])


def week_label(dt: datetime) -> str:
    y, w, _ = dt.astimezone(JST).isocalendar()
    return f"{y}-W{w:02d}"


def history_from_rows(rows: list[dict[str, Any]], weeks: int) -> dict[str, list[dict[str, Any]]]:
    """metrics(agent_weekly_activity) の行 → 社員ごとの週の並び（新しい順）"""
    days = sorted({str(r["recorded_at"])[:10] for r in rows}, reverse=True)[:weeks]
    hist: dict[str, list[dict[str, Any]]] = {}
    for d in days:
        for r in rows:
            if str(r["recorded_at"])[:10] != d:
                continue
            p = r.get("payload") or {}
            hist.setdefault(str(r["entity"]), []).append({
                "day": d, "signal": p.get("signal") or "⚪", "why": p.get("why") or "",
                "runs": p.get("runs"), "items": p.get("items"), "expected": p.get("expected"),
            })
    return hist


def history_from_report(rep: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    day = str(rep.get("until", ""))[:10]
    return {r["id"]: [{"day": day, "signal": r.get("signal") or "⚪", "why": r.get("why") or "",
                       "runs": r.get("runs"), "items": r.get("items"), "expected": r.get("expected")}]
            for r in rep.get("agents") or []}


def fetch_history(weeks: int) -> dict[str, list[dict[str, Any]]]:
    rows = rest("metrics", {"select": "entity,value,recorded_at,payload", "metric": "eq.agent_weekly_activity",
                            "order": "recorded_at.desc", "limit": str(60 * weeks)}) or []
    return history_from_rows(rows, weeks)


def fetch_decisions(since: datetime) -> list[dict[str, Any]]:
    return rest("owner_decisions", {
        "select": "id,decided_at,surface,action,employee,target_id,note,payload",
        "decided_at": f"gte.{since.isoformat()}", "order": "decided_at.desc", "limit": "5000",
    }) or []


# ---------- 判定（ネットワークなし） ----------

def employee_rates(rows: list[dict[str, Any]], since: datetime) -> dict[str, dict[str, int]]:
    """社員の提案に松野さんがどう判断したか（採った／見送った）。段階そのものの判断は除く"""
    out: dict[str, dict[str, int]] = {}
    for r in rows:
        emp = str(r.get("employee") or "").strip()
        if not emp or r.get("surface") == SURFACE:
            continue
        try:
            at = datetime.fromisoformat(str(r.get("decided_at")).replace("Z", "+00:00"))
        except ValueError:
            continue
        if at < since:
            continue
        oc = (r.get("payload") or {}).get("outcome") or outcome_of(str(r.get("action") or ""))
        c = out.setdefault(emp, {"n": 0, "take": 0, "ng": 0})
        if oc in ("take", "ng"):
            c["n"] += 1
            c[oc] += 1
    return out


def stage_decisions(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """提案キー（311:運用確認>運用）ごとの最新の判断"""
    out: dict[str, dict[str, Any]] = {}
    for r in sorted(rows, key=lambda x: str(x.get("decided_at") or ""), reverse=True):
        if r.get("surface") != SURFACE:
            continue
        k = str((r.get("payload") or {}).get("key") or "")
        if k and k not in out and r.get("action") in ("adopt", "skip", "defer"):
            out[k] = r
    return out


def _signals(h: list[dict[str, Any]]) -> list[str]:
    return [str(x.get("signal") or "⚪") for x in h]


def _streak(sigs: list[str], s: str) -> int:
    n = 0
    for x in sigs:
        if x != s:
            break
        n += 1
    return n


def propose(agents: list[dict[str, str]], hist: dict[str, list[dict[str, Any]]],
            rates: dict[str, dict[str, int]], decided: dict[str, dict[str, Any]],
            cfg: dict[str, Any], now: datetime) -> dict[str, list[dict[str, Any]]]:
    up = cfg.get("promote_ops") or {}
    chk = cfg.get("promote_check") or {}
    down = cfg.get("demote_ops") or {}
    cooldown = timedelta(weeks=int(cfg.get("skip_cooldown_weeks") or 4))
    proposals: list[dict[str, Any]] = []
    watch: list[dict[str, Any]] = []
    for a in agents:
        h = hist.get(a["id"]) or []
        sigs = _signals(h)
        latest = h[0] if h else None
        reasons: list[str] = []
        blockers: list[str] = []
        to = None
        if a["status"] == "運用確認":
            to = "運用"
            need = int(up.get("green_weeks") or 2)
            g = _streak(sigs, "🟢")
            reds = sigs[: int(up.get("no_red_weeks") or 4)].count("🔴")
            if g >= need:
                reasons.append(f"週次稼働が {g} 週続けて 🟢（{'・'.join(x['day'][5:] for x in h[:g])}）")
            elif not h:
                blockers.append("週次稼働の記録がまだない")
            else:
                blockers.append(f"🟢 が {g}/{need} 週（今週 {sigs[0]} {latest['why'] if latest else ''}）".strip())
            if reds:
                blockers.append(f"直近 {len(sigs[: int(up.get('no_red_weeks') or 4)])} 週に 🔴 が {reds} 回")
            rt = rates.get(a["id"]) or {"n": 0, "take": 0, "ng": 0}
            if rt["n"] >= int(up.get("decision_min_n") or 5):
                rate = rt["ng"] / rt["n"]
                line = f"松野さんの判断 {rt['n']} 件で採用 {rt['take']}・見送り {rt['ng']}（見送り {rate:.0%}）"
                if rate > float(up.get("max_ng_rate") or 0.3):
                    blockers.append(line + "→ 意図とずれが残る")
                else:
                    reasons.append(line)
            elif rt["n"]:
                reasons.append(f"松野さんの判断はまだ {rt['n']} 件（少ないので稼働の判定で見る）")
        elif a["status"] == "設計中":
            to = "運用確認"
            runs = latest.get("runs") if latest else None
            if latest and (runs or 0) >= int(chk.get("min_runs") or 1) and sigs[0] in (chk.get("ok_signals") or ["🟢", "🟡"]):
                reasons.append(f"今週 {runs} 回動いた（{sigs[0]} {latest['why']}）＝定時が動き始めた")
            elif not latest:
                blockers.append("動いた跡を数える場所が未登録（config/agent_weekly_activity.yaml）" if hist
                                else "週次稼働の記録がまだない")
            else:
                blockers.append(f"今週の稼働 {sigs[0]} {latest['why']}".strip())
        elif a["status"] == "運用":
            need = int(down.get("red_weeks") or 2)
            r = _streak(sigs, "🔴")
            if r >= need:
                to = "運用確認"
                reasons.append(f"週次稼働が {r} 週続けて 🔴（{latest['why'] if latest else ''}）")
            else:
                continue
        if not to:
            continue
        key = f"{a['id']}:{a['status']}>{to}"
        item = {
            "key": key, "id": a["id"], "name": a["name"], "from": a["status"], "to": to,
            "kind": "down" if STAGES.index(to) < STAGES.index(a["status"]) else "up",
            "reasons": reasons, "blockers": blockers,
            "weeks": [{"day": x["day"], "signal": x["signal"], "why": x["why"]} for x in h],
            "decisions": rates.get(a["id"]) or {"n": 0, "take": 0, "ng": 0},
        }
        last = decided.get(key)
        if last:
            at = datetime.fromisoformat(str(last["decided_at"]).replace("Z", "+00:00"))
            item["last_decision"] = {"action": last["action"], "at": last["decided_at"], "note": last.get("note")}
            pl = last.get("payload") or {}
            if last["action"] == "adopt":
                item["blockers"] = [("採用済み・registry に反映済み" if pl.get("registry_applied_at") else "採用済み・土曜 9:30 の 314 が反映")]
                watch.append(item)
                continue
            if last["action"] == "skip" and now - at < cooldown:
                item["blockers"].insert(0, f"前回見送り（{at.astimezone(JST):%m/%d}）{('：' + last['note']) if last.get('note') else ''}")
                watch.append(item)
                continue
        (proposals if not blockers else watch).append(item)
    order = {"down": 0, "up": 1}
    proposals.sort(key=lambda x: (order[x["kind"]], -STAGES.index(x["to"]), x["id"]))
    watch.sort(key=lambda x: (-STAGES.index(x["from"]), len(x["blockers"]), x["id"]))
    return {"proposals": proposals, "watch": watch}


def build(agents: list[dict[str, str]], hist: dict[str, list[dict[str, Any]]], decisions: list[dict[str, Any]],
          cfg: dict[str, Any], now: datetime, errors: list[str] | None = None) -> dict[str, Any]:
    pw = int((cfg.get("promote_ops") or {}).get("decision_window_days") or 28)
    rates = employee_rates(decisions, now - timedelta(days=pw))
    res = propose(agents, hist, rates, stage_decisions(decisions), cfg, now)
    counts = {s: sum(1 for a in agents if a["status"] == s) for s in STAGES}
    return {"generated_at": now.isoformat(timespec="seconds"), "week": week_label(now),
            "counts": counts, **res, "errors": errors or []}


# ---------- 出力 ----------

def _line(p: dict[str, Any]) -> str:
    arrow = "⬇️" if p["kind"] == "down" else "⬆️"
    return f"{arrow} {p['id']} {p['name']}：{p['from']}→{p['to']}"


def slack_lines(rep: dict[str, Any], limit: int = 5) -> list[str]:
    ps = rep.get("proposals") or []
    c = rep.get("counts") or {}
    head = f"段階: 設計中{c.get('設計中', 0)}・運用確認{c.get('運用確認', 0)}・運用{c.get('運用', 0)}"
    if not ps:
        return [head + "／今週の提案なし"]
    out = [head + f"／提案 {len(ps)} 件（/review で上げる・見送るを決めてください）"]
    out += [f"・{_line(p)}（{(p['reasons'] or [''])[0][:40]}）" for p in ps[:limit]]
    if len(ps) > limit:
        out.append(f"・ほか {len(ps) - limit} 件")
    return out


def render_md(rep: dict[str, Any]) -> str:
    lines = [f"# AI社員の段階の見直し {rep['week']}", ""]
    lines.append("## 提案")
    for p in rep["proposals"] or []:
        lines.append(f"- {_line(p)}")
        lines += [f"  - {x}" for x in p["reasons"]]
    if not rep["proposals"]:
        lines.append("- なし")
    lines += ["", "## 見守り（まだ）"]
    for p in rep["watch"]:
        lines.append(f"- {_line(p)}：{' / '.join(p['blockers'])}")
    return "\n".join(lines) + "\n"


def push(rep: dict[str, Any]) -> None:
    rest("sync_meta", {"on_conflict": "key"}, method="POST", body={
        "key": "agent_stage_review", "value": json.dumps(rep, ensure_ascii=False), "updated_at": rep["generated_at"]})


# ---------- 反映（採用分だけ） ----------

def set_registry_status(text: str, aid: str, frm: str, to: str) -> tuple[str, bool]:
    """agents: の '<aid>': ブロックの status を frm → to に。いまの status が frm でなければ触らない"""
    lines = text.split("\n")
    in_agents = False
    in_block = False
    for i, ln in enumerate(lines):
        if re.match(r"^agents:\s*$", ln):
            in_agents = True
            continue
        if in_agents and re.match(r"^\S", ln):
            in_agents = False
        if not in_agents:
            continue
        m = re.match(r"^  '?([^':\s]+)'?:\s*$", ln)
        if m:
            in_block = m.group(1) == aid
            continue
        if in_block and re.match(r"^    status:\s*", ln):
            cur = ln.split(":", 1)[1].strip()
            if cur != frm:
                return text, False
            lines[i] = f"    status: {to}"
            return "\n".join(lines), True
    return text, False


def pending_adoptions(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    latest = stage_decisions(rows)
    return [r for r in latest.values()
            if r["action"] == "adopt" and not (r.get("payload") or {}).get("registry_applied_at")]


def apply(rows: list[dict[str, Any]], *, dry: bool, commit: bool, registry: Path = REGISTRY) -> list[str]:
    done = []
    for r in sorted(pending_adoptions(rows), key=lambda x: str(x["decided_at"])):
        pl = dict(r.get("payload") or {})
        aid, frm, to = str(pl.get("agent_id") or r.get("employee")), str(pl.get("from")), str(pl.get("to"))
        text = registry.read_text(encoding="utf-8")
        new, ok = set_registry_status(text, aid, frm, to)
        if not ok:
            print(f"{LOG}: skip {aid} {frm}→{to}（registry の status が {frm} ではない）", file=sys.stderr)
            continue
        done.append(f"{aid} {frm}→{to}")
        if dry:
            continue
        registry.write_text(new, encoding="utf-8")
        subprocess.run([sys.executable, str(REPO / "scripts" / "jarvis_agent_team_status_sync.py")], check=True, cwd=REPO)
        pl["registry_applied_at"] = datetime.now(JST).isoformat(timespec="seconds")
        if commit:
            subprocess.run(["git", "add", "-A", "docs/AIエージェントチーム", "apps/jarvis-dashboard/data/agentTeam.json"],
                           check=True, cwd=REPO)
            why = (r.get("note") or "").strip() or "（理由の記入なし）"
            subprocess.run(["git", "commit", "-q", "-m",
                            f"agent-team({aid}): {frm} → {to}\n\n週次レビューで松野さんが採用（判断ログ id={r['id']}）\n理由: {why}"],
                           check=True, cwd=REPO)
        rest("owner_decisions", {"id": f"eq.{r['id']}"}, method="PATCH", body={"payload": pl})
    return done


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--push", action="store_true")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--apply", action="store_true", help="採用済みの段階変更を registry に反映")
    ap.add_argument("--commit", action="store_true")
    a = ap.parse_args(argv)
    cfg = load_cfg()
    now = datetime.now(JST)

    if a.apply:
        rows = fetch_decisions(now - timedelta(weeks=12))
        done = apply([r for r in rows if r.get("surface") == SURFACE], dry=a.dry_run, commit=a.commit)
        print("\n".join(done) if done else "反映する採用はありません")
        return 0

    errors: list[str] = []
    weeks = int(cfg.get("history_weeks") or 6)
    try:
        hist = fetch_history(weeks)
    except Exception as e:  # noqa: BLE001
        errors.append(f"週次稼働の履歴を読めず（{str(e)[:100]}）: 手元の最新だけで判定")
        try:
            hist = history_from_report(json.loads(ACTIVITY_LATEST.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            hist = {}
    try:
        decisions = fetch_decisions(now - timedelta(weeks=12))
    except Exception as e:  # noqa: BLE001
        errors.append(f"判断ログを読めず（{str(e)[:100]}）")
        decisions = []
    rep = build(load_agents(), hist, decisions, cfg, now, errors)

    STATE_DIR.mkdir(parents=True, exist_ok=True)
    (STATE_DIR / "latest.json").write_text(json.dumps(rep, ensure_ascii=False, indent=2), encoding="utf-8")
    (STATE_DIR / f"week_{now:%Y%m%d}.md").write_text(render_md(rep), encoding="utf-8")
    if a.json:
        print(json.dumps(rep, ensure_ascii=False, indent=2))
    else:
        print(render_md(rep))
    if a.push and not a.dry_run:
        try:
            push(rep)
        except Exception as e:  # noqa: BLE001
            print(f"{LOG}: push FAIL: {e}", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
