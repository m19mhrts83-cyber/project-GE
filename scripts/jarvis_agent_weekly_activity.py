#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""AI社員・Grok Bot の週次稼働（エラーだけでなく「どれだけ機能したか」）を数える。

  cd ~/git-repos && set -a && source .env.jarvis_private && set +a
  ~/selenium_env/venv/bin/python scripts/jarvis_agent_weekly_activity.py            # 集計して表示＋写し保存
  ~/selenium_env/venv/bin/python scripts/jarvis_agent_weekly_activity.py --push     # Supabase metrics／sync_meta へ
  ~/selenium_env/venv/bin/python scripts/jarvis_agent_weekly_activity.py --dry-run  # 保存しない

入口: 土曜 9:00 の launchd（weekly_review_314_runner.sh に相乗り。Mac のログを読むため Mac）
数え方: config/agent_weekly_activity.yaml（社員ごとの「動いた跡」の置き場）
出力:
  - .jarvis_state/agent_weekly_activity/latest.json（314 の Slack 週次がここを読む）
  - Supabase（個人 jarvis-dashboard・既存表のみ）
      metrics: metric=agent_weekly_activity, entity=社員番号 or grok:<bot>, value=件数, payload=内訳
      sync_meta: key=agent_weekly_activity（最新の全体 JSON）
  - ダッシュ /agent-team「週次稼働」タブ

AI は使わない（数えるだけ）。取れないものは推測で埋めず「未計測」にする。
収集元が落ちたときは errors に残し、黙って 0 にしない。
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
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Iterable

REPO = Path(os.environ.get("JARVIS_AGENT_ACTIVITY_REPO") or Path(__file__).resolve().parents[1])
CONFIG = Path(os.environ.get("JARVIS_AGENT_ACTIVITY_CONFIG") or REPO / "config" / "agent_weekly_activity.yaml")
TEAM_JSON = REPO / "apps" / "jarvis-dashboard" / "data" / "agentTeam.json"
SLACK_HUB = REPO / "config" / "slack_ai_team_hub.yaml"
OUT_DIR = REPO / ".jarvis_state" / "agent_weekly_activity"
LOG_ROOT = Path(os.environ.get("JARVIS_AGENT_ACTIVITY_LOG_ROOT") or Path.home() / "Library" / "Logs")
JST = timezone(timedelta(hours=9))
LOG = "📎 AI社員 週次稼働"
SIGNAL_RE = re.compile(r"判定[:：]\s*(🟢|🟡|🔴|⚪|:large_green_circle:|:large_yellow_circle:|:red_circle:|:white_circle:)")
SIGNAL_NORM = {
    ":large_green_circle:": "🟢", ":large_yellow_circle:": "🟡", ":red_circle:": "🔴", ":white_circle:": "⚪",
}
# 1行目の社員番号（日付 11/14 や金額は拾わない）
AGENT_NO_RE = re.compile(r"(?<![\d/.,:])([1-8][1-9]\d)(?![\d/.,:万円件%])")
GROK_CODE_RE = re.compile(r"(?<![A-Za-z0-9])S(1[0-3]|[1-9])(?!\d)")


# ---------- 基本 ----------

def load_yaml(path: Path) -> dict[str, Any]:
    import yaml  # selenium_env にある

    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def parse_stamp(s: str) -> datetime | None:
    """'20261114_074025' / '20261114' / '2026-11-14 07:40:25' を JST として読む"""
    s = s.strip()
    for fmt in ("%Y%m%d_%H%M%S", "%Y%m%d", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(s, fmt).replace(tzinfo=JST)
        except ValueError:
            continue
    return None


def empty_row() -> dict[str, Any]:
    return {
        "runs": None, "worked": None, "items": None, "ok": None, "ng": None, "fail": None,
        "pending": None, "pending_samples": [], "retries": None, "slack_posts": 0, "slack_signals": {},
        "last_at": None, "sources": [], "notes": [],
    }


def bump(row: dict[str, Any], key: str, n: int) -> None:
    row[key] = (row[key] or 0) + n


def later(a: str | None, b: str | None) -> str | None:
    if not a:
        return b
    if not b:
        return a
    return max(a, b)


# ---------- 収集: 追記型ログ（======== 日時 ======== 区切り） ----------

def count_log_blocks(text: str, spec: dict[str, Any], since: datetime, until: datetime) -> dict[str, Any]:
    head = re.compile(spec["header_regex"])
    items_re = re.compile(spec["items_regex"], re.M) if spec.get("items_regex") else None
    ok_re = re.compile(spec["ok_regex"], re.M) if spec.get("ok_regex") else None
    ng_re = re.compile(spec["ng_regex"], re.M) if spec.get("ng_regex") else None
    fail_re = re.compile(spec["fail_regex"], re.M) if spec.get("fail_regex") else None
    retry_re = re.compile(spec["retry_regex"], re.M) if spec.get("retry_regex") else None
    blocks: list[tuple[datetime, list[str]]] = []
    cur: tuple[datetime, list[str]] | None = None
    for line in text.splitlines():
        m = head.match(line)
        if m:
            ts = parse_stamp(m.group(1))
            cur = (ts, []) if ts else None
            if cur:
                blocks.append(cur)
            continue
        if cur:
            cur[1].append(line)
    out = {"runs": 0, "worked": 0, "items": 0, "ok": 0, "ng": 0, "fail": 0, "retries": 0,
           "last_at": None, "last_worked_at": None}
    for ts, lines in blocks:
        if not (since <= ts < until):
            continue
        body = "\n".join(lines)
        out["runs"] += 1
        out["last_at"] = ts.isoformat()
        n = 0
        if items_re:
            # グループありなら数字を足す、なしなら当たった行の数
            n = sum(int(x) for x in items_re.findall(body)) if items_re.groups else len(items_re.findall(body))
        if ok_re:
            out["ok"] += len(ok_re.findall(body))
        if ng_re:
            out["ng"] += len(ng_re.findall(body))
        if fail_re and fail_re.search(body):
            out["fail"] += 1
        if retry_re and retry_re.search(body) and not n:
            out["retries"] += 1
        if n:
            out["worked"] += 1
            out["items"] += n
            out["last_worked_at"] = ts.isoformat()
    return out


def count_pending_dir(d: Path, skip_regex: str) -> tuple[int, list[str]]:
    """持ち越し（詰まり）＝受け口に残ったままの依頼。集計した時点の数"""
    if not d.is_dir():
        return 0, []
    skip = re.compile(skip_regex)
    names = sorted(p.name for p in d.glob("*.md") if p.is_file() and not skip.search(p.name))
    return len(names), names[:3]


# ---------- 収集: 1回1ファイル ----------

def count_stamped_files(paths: Iterable[Path], pattern: str, since: datetime, until: datetime,
                        items_regex: str | None = None, fail_regex: str | None = None,
                        read: Callable[[Path], str] | None = None) -> dict[str, Any]:
    pat = re.compile(pattern)
    items_re = re.compile(items_regex, re.M) if items_regex else None
    fail_re = re.compile(fail_regex, re.M) if fail_regex else None
    rd = read or (lambda p: p.read_text(encoding="utf-8", errors="replace"))
    out = {"runs": 0, "worked": 0, "items": 0, "fail": 0, "last_at": None}
    for p in paths:
        m = pat.search(p.name)
        ts = parse_stamp(m.group(1)) if m else None
        if not ts or not (since <= ts < until):
            continue
        out["runs"] += 1
        out["last_at"] = later(out["last_at"], ts.isoformat())
        if items_re or fail_re:
            try:
                body = rd(p)
            except OSError:
                continue
            if items_re:
                n = sum(int(x) for x in items_re.findall(body))
                if n:
                    out["worked"] += 1
                    out["items"] += n
            if fail_re and fail_re.search(body):
                out["fail"] += 1
    if not items_regex:
        out["worked"] = out["runs"] - out["fail"]
        out["items"] = None
    return out


# ---------- 収集: GHA ----------

def workflow_names() -> dict[str, str]:
    """ファイル名 → name:（gh run list は name で返す）"""
    out = {}
    for wf in (REPO / ".github" / "workflows").glob("*.yml"):
        m = re.search(r"(?m)^name:\s*(.+)$", wf.read_text(encoding="utf-8"))
        out[wf.name] = (m.group(1).strip().strip("'\"") if m else wf.stem)
    return out


def fetch_gha_runs(since: datetime) -> list[dict[str, Any]]:
    raw = subprocess.run(
        ["gh", "run", "list", "--limit", "1000", "--created", f">={since.strftime('%Y-%m-%d')}",
         "--json", "workflowName,conclusion,createdAt,status"],
        cwd=str(REPO), capture_output=True, text=True, timeout=180,
    )
    if raw.returncode != 0:
        raise RuntimeError((raw.stderr or raw.stdout).strip()[:200])
    return json.loads(raw.stdout or "[]")


def count_gha(runs: list[dict[str, Any]], names: list[str], since: datetime, until: datetime) -> dict[str, Any]:
    out = {"runs": 0, "worked": 0, "fail": 0, "last_at": None}
    for r in runs:
        if r.get("workflowName") not in names:
            continue
        ts = datetime.fromisoformat(str(r.get("createdAt", "")).replace("Z", "+00:00"))
        if not (since <= ts < until):
            continue
        c = r.get("conclusion") or ""
        if c in ("skipped", "cancelled") or r.get("status") not in (None, "completed"):
            continue
        out["runs"] += 1
        out["last_at"] = later(out["last_at"], ts.astimezone(JST).isoformat())
        if c == "success":
            out["worked"] += 1
        elif c in ("failure", "timed_out", "startup_failure"):
            out["fail"] += 1
    return out


# ---------- 収集: Slack ----------

def slack_token() -> str:
    for k in ("SLACK_BOT_TOKEN", "SLACK_USER_TOKEN", "SLACK_TOKEN"):
        v = (os.environ.get(k) or "").strip()
        if v:
            return v
    return ""


def fetch_slack(channel_ids: list[str], since: datetime, token: str) -> list[dict[str, Any]]:
    msgs: list[dict[str, Any]] = []
    for cid in channel_ids:
        cursor = ""
        for _ in range(20):
            q = {"channel": cid, "oldest": f"{since.timestamp():.0f}", "limit": "200"}
            if cursor:
                q["cursor"] = cursor
            req = urllib.request.Request(
                "https://slack.com/api/conversations.history?" + urllib.parse.urlencode(q),
                headers={"Authorization": f"Bearer {token}"},
            )
            with urllib.request.urlopen(req, timeout=60) as r:
                data = json.loads(r.read())
            if not data.get("ok"):
                raise RuntimeError(f"slack {cid}: {data.get('error')}")
            for m in data.get("messages", []):
                m["_channel"] = cid
                msgs.append(m)
            cursor = (data.get("response_metadata") or {}).get("next_cursor") or ""
            if not cursor:
                break
    return msgs


def slack_text(m: dict[str, Any]) -> str:
    t = m.get("text") or ""
    if not t:
        for b in m.get("blocks") or []:
            tx = (b.get("text") or {}).get("text") if isinstance(b.get("text"), dict) else None
            if tx:
                t += tx + "\n"
    return t


def attribute_slack(msg: dict[str, Any], agent_ids: set[str], grok_bots: dict[str, dict[str, Any]]) -> list[str]:
    """投稿の持ち主（社員番号 or grok:<bot>）。1行目＋送信名で決める"""
    text = slack_text(msg)
    first = (text.strip().splitlines() or [""])[0]
    head = f"{msg.get('username') or ''} {first}"
    owners = [f for f in AGENT_NO_RE.findall(head) if f in agent_ids]
    if owners:
        return [owners[0]]
    for code in GROK_CODE_RE.findall(head):
        for key, bot in grok_bots.items():
            if str(bot.get("code")) == f"S{code}":
                return [f"grok:{key}"]
    for key, bot in grok_bots.items():
        rx = bot.get("slack_regex")
        if rx and re.search(rx, head):
            return [f"grok:{key}"]
    return []


def slack_signal(text: str) -> str | None:
    m = SIGNAL_RE.search(text)
    if not m:
        return None
    return SIGNAL_NORM.get(m.group(1), m.group(1))


# ---------- 収集: Grok の成果物メール ----------

def fetch_grok_mail(query: str, since: datetime) -> list[dict[str, str]]:
    sys.path.insert(0, str(REPO / "scripts"))
    from jarvis_grok_bucho_mail_apply import gmail_service  # noqa: E402

    svc = gmail_service()
    q = f"{query} after:{since.strftime('%Y/%m/%d')}"
    out: list[dict[str, str]] = []
    token = None
    for _ in range(10):
        res = svc.users().messages().list(userId="me", q=q, maxResults=100, pageToken=token).execute()
        for m in res.get("messages", []):
            full = svc.users().messages().get(
                userId="me", id=m["id"], format="metadata", metadataHeaders=["Subject"]).execute()
            subj = next((h["value"] for h in full.get("payload", {}).get("headers", [])
                         if h.get("name", "").lower() == "subject"), "")
            ts = datetime.fromtimestamp(int(full.get("internalDate", "0")) / 1000, tz=JST)
            out.append({"subject": subj, "at": ts.isoformat()})
        token = res.get("nextPageToken")
        if not token:
            break
    return out


def count_grok_mail(mails: list[dict[str, str]], bot: dict[str, Any], since: datetime, until: datetime) -> dict[str, Any]:
    kinds: Counter = Counter()
    outcomes: Counter = Counter()
    last = None
    for m in mails:
        ts = datetime.fromisoformat(m["at"])
        if not (since <= ts < until):
            continue
        for kind, rx in (bot.get("subjects") or {}).items():
            if re.search(rx, m["subject"]):
                kinds[kind] += 1
                last = later(last, m["at"])
                # 結論は件名の後ろのほうにある（いちばん後ろに出てくる結論語を採る）
                best, pos = None, -1
                for oc, orx in (bot.get("outcomes") or {}).items():
                    hits = [mm.start() for mm in re.finditer(orx, m["subject"])]
                    if hits and hits[-1] > pos:
                        best, pos = oc, hits[-1]
                if best:
                    outcomes[best] += 1
                break
    return {"kinds": dict(kinds), "outcomes": dict(outcomes), "last_at": last}


# ---------- 判定 ----------

def judge(row: dict[str, Any], expected: int | None, has_source: bool, measured: bool = True) -> tuple[str, str]:
    runs = row["runs"]
    fail = row["fail"] or 0
    if not has_source and not row["slack_posts"]:
        return "⚪", "数える場所が未設定"
    if not measured and not runs and not row["slack_posts"]:
        return "⚪", "収集元を読めず未計測"
    if (runs or 0) == 0 and not row["slack_posts"]:
        return ("🔴", "今週は動いた跡なし") if expected else ("⚪", "今週は出番なし")
    if runs and fail and fail / runs >= 0.3:
        return "🔴", f"失敗 {fail}/{runs} 回"
    if row["pending"]:
        return "🟡", f"持ち越し {row['pending']} 件（処理できず次回へ）"
    if row.get("retries"):
        return "🟡", f"処理できず再試行 {row['retries']} 回（詰まり）"
    if fail:
        return "🟡", f"失敗 {fail} 回"
    basis = runs if runs is not None else row["slack_posts"]
    if expected and basis < expected * 0.6:
        return "🟡", f"起動 {basis}/{expected} 回（予定より少ない）"
    if row["worked"] == 0 and row["items"] == 0:
        return "🟢", "起動は正常・処理対象なし（空振り）"
    return "🟢", "回っています"


# ---------- 全体 ----------

def build_report(cfg: dict[str, Any], now: datetime, *, gha_runs: list[dict[str, Any]] | None,
                 slack_msgs: list[dict[str, Any]] | None, grok_mails: list[dict[str, str]] | None,
                 errors: list[str], log_root: Path = LOG_ROOT, repo: Path = REPO) -> dict[str, Any]:
    days = int(cfg.get("window_days") or 7)
    since = now - timedelta(days=days)
    team = json.loads(TEAM_JSON.read_text(encoding="utf-8"))
    agents_meta = {a["id"]: a for a in team.get("agents", []) if "廃止" not in str(a.get("status", ""))}
    acfg: dict[str, dict[str, Any]] = cfg.get("agents") or {}
    gcfg = cfg.get("grok") or {}
    gbots: dict[str, dict[str, Any]] = gcfg.get("bots") or {}
    wf_names = workflow_names()

    rows: dict[str, dict[str, Any]] = {}
    for aid, meta in agents_meta.items():
        spec = acfg.get(aid) or {}
        # 候補（未着手）で数える場所もない社員は載せない
        if meta.get("status") == "候補" and not spec:
            continue
        row = empty_row()
        row.update({"id": aid, "name": meta.get("name", ""), "status": meta.get("status", ""),
                    "kind": "ai", "expected": spec.get("expected_per_week")})
        if spec.get("note"):
            row["notes"].append(spec["note"])
        has_source = False

        if spec.get("gha"):
            has_source = True
            names = [wf_names.get(f, f) for f in spec["gha"].get("workflows", [])]
            if gha_runs is None:
                row["notes"].append("GHA 未取得")
            else:
                g = count_gha(gha_runs, names, since, now)
                for k in ("runs", "worked", "fail"):
                    bump(row, k, g[k])
                row["last_at"] = later(row["last_at"], g["last_at"])
                row["sources"].append("GHA")

        if spec.get("log_blocks"):
            has_source = True
            lb = spec["log_blocks"]
            p = log_root / lb["path"]
            if p.is_file():
                b = count_log_blocks(p.read_text(encoding="utf-8", errors="replace"), lb, since, now)
                for k in ("runs", "worked", "items", "ok", "ng", "fail", "retries"):
                    bump(row, k, b[k])
                row["last_at"] = later(row["last_at"], b["last_worked_at"] or b["last_at"])
                row["sources"].append("Macログ")
            else:
                row["notes"].append(f"ログなし: {lb['path']}")

        if spec.get("output_files"):
            # 成果物（1件1ファイル）で件数と OK/NG を数え直す。CLI 直呼び（経路B）も入る
            of = spec["output_files"]
            pat = re.compile(of["pattern"])
            n = ok = ng = 0
            for p in sorted(repo.glob(of["glob"])):
                m = pat.search(p.name)
                ts = parse_stamp(m.group(1)) if m else None
                if not ts or not (since <= ts < now):
                    continue
                n += 1
                try:
                    v = str(json.loads(p.read_text(encoding="utf-8")).get(of.get("result_field", "overall"), ""))
                except (OSError, ValueError):
                    v = ""
                ok += v == "OK"
                ng += v == "NG"
            row["items"], row["ok"], row["ng"] = n, ok, ng
            if "成果物" not in row["sources"]:
                row["sources"].append("成果物")

        if spec.get("pending_dir"):
            pd = spec["pending_dir"]
            n, samples = count_pending_dir(repo / pd["path"], pd.get("skip_regex", r"^(README|example_)"))
            row["pending"] = n
            row["pending_samples"] = samples

        if spec.get("log_files"):
            has_source = True
            lf = spec["log_files"]
            d = log_root / lf["dir"]
            if d.is_dir():
                f = count_stamped_files(sorted(d.iterdir()), lf["pattern"], since, now,
                                        lf.get("items_regex"), lf.get("fail_regex"))
                for k in ("runs", "worked", "fail"):
                    bump(row, k, f[k])
                if f["items"] is not None:
                    bump(row, "items", f["items"])
                row["last_at"] = later(row["last_at"], f["last_at"])
                row["sources"].append("Macログ")
            else:
                row["notes"].append(f"ログなし: {lf['dir']}")

        if spec.get("files"):
            has_source = True
            fs = spec["files"]
            f = count_stamped_files(sorted(repo.glob(fs["glob"])), fs["pattern"], since, now)
            for k in ("runs", "worked"):
                bump(row, k, f[k])
            row["last_at"] = later(row["last_at"], f["last_at"])
            row["sources"].append("成果物")

        row["_has_source"] = has_source
        row["_measured"] = bool(row["sources"]) or not has_source
        row["_slack_items_regex"] = spec.get("slack_items_regex")
        rows[aid] = row

    # Grok
    for key, bot in gbots.items():
        row = empty_row()
        exp = bot.get("expected") or {}
        row.update({"id": f"grok:{key}", "name": bot.get("name", key), "code": bot.get("code"),
                    "status": "Grok", "kind": "grok", "expected": sum(exp.values()) or None,
                    "kinds": {}, "kinds_expected": exp, "outcomes": {}})
        if bot.get("note"):
            row["notes"].append(bot["note"])
        has_source = bool(bot.get("subjects"))
        if has_source:
            if grok_mails is None:
                row["notes"].append("報告メール 未取得")
            else:
                g = count_grok_mail(grok_mails, bot, since, now)
                row["kinds"] = g["kinds"]
                row["outcomes"] = g["outcomes"]
                total = sum(g["kinds"].values())
                row["runs"] = total
                row["worked"] = total
                row["items"] = total
                row["last_at"] = g["last_at"]
                row["sources"].append("報告メール")
        row["_has_source"] = has_source
        row["_measured"] = bool(row["sources"]) or not has_source
        row["_slack_items_regex"] = None
        rows[row["id"]] = row

    # Slack（全員共通）
    if slack_msgs is None:
        errors.append("Slack 未取得（報告数は数えていません）")
    else:
        ids = {k for k in rows if not k.startswith("grok:")}
        for m in slack_msgs:
            ts = datetime.fromtimestamp(float(m.get("ts", "0")), tz=JST)
            if not (since <= ts < now):
                continue
            for owner in attribute_slack(m, ids, gbots):
                row = rows.get(owner)
                if not row:
                    continue
                row["slack_posts"] += 1
                sig = slack_signal(slack_text(m))
                if sig:
                    row["slack_signals"][sig] = row["slack_signals"].get(sig, 0) + 1
                rx = row.get("_slack_items_regex")
                if rx:
                    mm = re.search(rx, slack_text(m))
                    if mm:
                        bump(row, "items", int(mm.group(1)))
                row["last_at"] = later(row["last_at"], ts.isoformat())
                if "Slack" not in row["sources"]:
                    row["sources"].append("Slack")

    # Slack しか数える場所がない社員は、報告数を起動回数とみなす
    for row in rows.values():
        if row["runs"] is None and not row["_has_source"] and row["slack_posts"]:
            row["runs"] = row["slack_posts"]
            row["notes"].append("起動回数は Slack の報告数で代用")
        sig, why = judge(row, row["expected"], row["_has_source"], row["_measured"])
        row["signal"], row["why"] = sig, why
        row.pop("_has_source", None)
        row.pop("_measured", None)
        row.pop("_slack_items_regex", None)

    order = {"🔴": 0, "🟡": 1, "🟢": 2, "⚪": 3}
    ai = sorted((r for r in rows.values() if r["kind"] == "ai"), key=lambda r: r["id"])
    grok = [r for r in rows.values() if r["kind"] == "grok"]
    summary = Counter(r["signal"] for r in rows.values())
    worked = sum(1 for r in rows.values() if (r["worked"] or 0) > 0 or (r["items"] or 0) > 0)
    return {
        "generated_at": now.isoformat(timespec="seconds"),
        "since": since.isoformat(timespec="seconds"),
        "until": now.isoformat(timespec="seconds"),
        "summary": {s: summary.get(s, 0) for s in order},
        "worked_agents": worked,
        "total_agents": len(rows),
        "agents": ai,
        "grok": grok,
        "attention": [
            {"id": r["id"], "name": r["name"], "signal": r["signal"], "why": r["why"]}
            for r in sorted(rows.values(), key=lambda r: (order[r["signal"]], r["id"]))
            if r["signal"] in ("🔴", "🟡")
        ],
        "errors": errors,
    }


# ---------- 書き出し ----------

def fmt(v: Any) -> str:
    return "—" if v is None else str(v)


def render_md(rep: dict[str, Any]) -> str:
    s = rep["summary"]
    lines = [
        f"# AI社員 週次稼働 {rep['until'][:10]}",
        "",
        f"対象: {rep['since'][:16]} 〜 {rep['until'][:16]}",
        f"機能した社員 {rep['worked_agents']}/{rep['total_agents']} ・ 🟢{s['🟢']} 🟡{s['🟡']} 🔴{s['🔴']} ⚪{s['⚪']}",
        "",
        "| 社員 | 判定 | 起動 | 実働 | 件数 | 失敗 | 報告 | ひとこと |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for r in rep["agents"] + rep["grok"]:
        lines.append(
            f"| {r['id']} {r['name']} | {r['signal']} | {fmt(r['runs'])} | {fmt(r['worked'])} | {fmt(r['items'])} "
            f"| {fmt(r['fail'])} | {r['slack_posts']} | {r['why']} |"
        )
    if rep["errors"]:
        lines += ["", "## 収集できなかったもの", ""] + [f"- {e}" for e in rep["errors"]]
    return "\n".join(lines) + "\n"


def slack_lines(rep: dict[str, Any], limit: int = 6) -> list[str]:
    """314 週次の Slack に足す数行（🟡 は週次まとめ）"""
    s = rep["summary"]
    out = [f"稼働: 機能した社員 {rep['worked_agents']}/{rep['total_agents']}（🟢{s['🟢']} 🟡{s['🟡']} 🔴{s['🔴']} ⚪{s['⚪']}）"]
    for a in rep["attention"][:limit]:
        out.append(f"・{a['signal']} {a['id'].replace('grok:', 'Grok ')} {a['name']}: {a['why']}"[:70])
    if len(rep["attention"]) > limit:
        out.append(f"・ほか{len(rep['attention']) - limit}件 → ダッシュ /agent-team 週次稼働")
    return out


def metric_rows(rep: dict[str, Any]) -> list[dict[str, Any]]:
    day = rep["until"][:10]
    rows = []
    for r in rep["agents"] + rep["grok"]:
        value = r["items"] if r["items"] is not None else (r["worked"] if r["worked"] is not None else r["runs"])
        if value is None:
            value = 0
        payload = {k: v for k, v in r.items() if k not in ("id",)}
        payload["period"] = {"since": rep["since"], "until": rep["until"]}
        rows.append({"metric": "agent_weekly_activity", "entity": r["id"], "value": float(value),
                     "unit": "items", "recorded_at": day, "payload": payload})
    return rows


def push_supabase(rep: dict[str, Any]) -> bool:
    url = (os.environ.get("JARVIS_SUPABASE_URL") or "").strip()
    key = (os.environ.get("JARVIS_SUPABASE_SERVICE_ROLE_KEY") or "").strip()
    if not url or not key:
        print(f"{LOG}: supabase skip（JARVIS_SUPABASE_* 未設定）", file=sys.stderr)
        return False
    try:
        from supabase import create_client

        sb = create_client(url, key)
        sb.table("metrics").upsert(metric_rows(rep), on_conflict="metric,entity,recorded_at").execute()
        sb.table("sync_meta").upsert(
            {"key": "agent_weekly_activity", "value": json.dumps(rep, ensure_ascii=False),
             "updated_at": rep["generated_at"]}, on_conflict="key").execute()
        return True
    except Exception as e:  # noqa: BLE001
        print(f"{LOG}: supabase FAIL: {e}", file=sys.stderr)
        return False


def collect_all(cfg: dict[str, Any], now: datetime) -> dict[str, Any]:
    days = int(cfg.get("window_days") or 7)
    since = now - timedelta(days=days)
    errors: list[str] = []

    gha_runs = None
    try:
        gha_runs = fetch_gha_runs(since)
    except Exception as e:  # noqa: BLE001
        errors.append(f"GHA 取得失敗: {str(e)[:120]}")

    slack_msgs = None
    token = slack_token()
    if token:
        try:
            hub = load_yaml(SLACK_HUB).get("channels") or {}
            ids = [hub[c]["id"] for c in cfg.get("slack_channels", []) if c in hub]
            slack_msgs = fetch_slack(ids, since, token)
        except Exception as e:  # noqa: BLE001
            errors.append(f"Slack 取得失敗: {str(e)[:120]}")
    else:
        errors.append("Slack トークン未設定（SLACK_BOT_TOKEN）")

    grok_mails = None
    q = (cfg.get("grok") or {}).get("gmail_query")
    if q:
        try:
            grok_mails = fetch_grok_mail(q, since)
        except Exception as e:  # noqa: BLE001
            errors.append(f"Grok 報告メール取得失敗: {str(e)[:120]}")

    return build_report(cfg, now, gha_runs=gha_runs, slack_msgs=slack_msgs, grok_mails=grok_mails, errors=errors)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true", help="写しを保存しない")
    ap.add_argument("--push", action="store_true", help="Supabase metrics／sync_meta へ")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    cfg = load_yaml(CONFIG)
    rep = collect_all(cfg, datetime.now(JST))
    if not args.dry_run:
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        (OUT_DIR / "latest.json").write_text(json.dumps(rep, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        (OUT_DIR / f"week_{rep['until'][:10].replace('-', '')}.md").write_text(render_md(rep), encoding="utf-8")
    if args.push and not args.dry_run:
        print(f"{LOG}: push {'ok' if push_supabase(rep) else 'failed'}", file=sys.stderr)
    print(json.dumps(rep, ensure_ascii=False, indent=2) if args.json else render_md(rep))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
