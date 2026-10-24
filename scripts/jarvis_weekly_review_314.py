#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""314 業務品質監査 — 週次の機械チェック（AI を使わない事実収集）。

  cd ~/git-repos && set -a && source .env.jarvis_private && set +a
  ~/selenium_env/venv/bin/python scripts/jarvis_weekly_review_314.py --dry-run
  ~/selenium_env/venv/bin/python scripts/jarvis_weekly_review_314.py --post

入口: launchd 土曜 9:00（Mac。launchd ログを読むため GHA ではなく Mac）
確認: 読むだけ。修正は 30 分後の Claude 定期タスク（判断）→ PR
履歴: .jarvis_state/weekly_review_314/facts_YYYYMMDD.md ／ latest.json
停止: JARVIS_WEEKLY_REVIEW_314_DISABLE=1

正本: docs/AIエージェントチーム/300_品質・タスク運用管理室/314_業務品質監査係/CLAUDE.md
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
OUT_DIR = REPO / ".jarvis_state" / "weekly_review_314"
LOG_ROOT = Path.home() / "Library" / "Logs"
JST = timezone(timedelta(hours=9))
LOG = "📎 314 業務品質監査"

# 予定より何分遅れたら「時刻ずれ」とみなすか
DELAY_FLAG_MIN = 60
# 同じエラー文が週に何回出たら「繰り返しエラー」とみなすか
REPEAT_FLAG = 5
ERROR_RE = re.compile(
    r"Traceback|Error|FAIL|not_in_channel|HTTP [45]\d\d|❌|soft-fail", re.I
)
# 「failed=0」「failed: なし」のような正常の集計行はエラーとみなさない
ZERO_COUNT_RE = re.compile(r"\b(fail|failed|errors?)\s*[=:]?\s*(0|なし)(?!\d)", re.I)
AI_CALL_RE = re.compile(
    r"openai|anthropic|chat\.completions|find_cursor_agent|launch_cloud_agent"
    r"|api\.x\.ai|generativelanguage|claude -p|cursor-agent"
)


def _run(cmd: list[str], *, timeout: int = 120) -> str:
    r = subprocess.run(
        cmd, cwd=str(REPO), capture_output=True, text=True, timeout=timeout
    )
    if r.returncode != 0:
        raise RuntimeError(f"{' '.join(cmd[:3])}: {r.stderr.strip()[:200]}")
    return r.stdout


# ---- cron（GHA は UTC）-------------------------------------------------------


def _cron_field(spec: str, value: int, lo: int, hi: int) -> bool:
    for part in spec.split(","):
        step = 1
        if "/" in part:
            part, s = part.split("/", 1)
            step = int(s)
        if part == "*":
            a, b = lo, hi
        elif "-" in part:
            a, b = (int(x) for x in part.split("-", 1))
        else:
            a = b = int(part)
        if a <= value <= b and (value - a) % step == 0:
            return True
    return False


def cron_matches(expr: str, dt: datetime) -> bool:
    mi, ho, dom, mon, dow = expr.split()
    return (
        _cron_field(mi, dt.minute, 0, 59)
        and _cron_field(ho, dt.hour, 0, 23)
        and _cron_field(dom, dt.day, 1, 31)
        and _cron_field(mon, dt.month, 1, 12)
        and _cron_field(dow, (dt.weekday() + 1) % 7, 0, 6)
    )


def schedule_delay_min(exprs: list[str], created: datetime) -> float | None:
    """created 以前で最も近い予定時刻からの遅れ（分）。24h 内に無ければ None。"""
    t = created.replace(second=0, microsecond=0)
    for i in range(24 * 60):
        cand = t - timedelta(minutes=i)
        if any(cron_matches(e, cand) for e in exprs):
            return (created - cand).total_seconds() / 60.0
    return None


def workflow_crons() -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for wf in sorted((REPO / ".github" / "workflows").glob("*.yml")):
        crons = re.findall(r"cron:\s*[\"']([^\"']+)[\"']", wf.read_text(encoding="utf-8"))
        if crons:
            out[wf.name] = crons
    return out


# ---- 収集 --------------------------------------------------------------------


def collect_commits(since: datetime) -> dict[str, Any]:
    raw = _run(
        ["git", "log", "origin/main", f"--since={since.isoformat()}", "--pretty=%h %s"]
    )
    lines = [x for x in raw.splitlines() if x.strip()]
    diff = _run(
        [
            "git", "log", "origin/main", f"--since={since.isoformat()}", "-p",
            "--pretty=COMMIT %h", "--", "*.py", "*.ts", "*.yml", "*.sh",
            # 検出パターンを書いている自分自身は除く
            ":!scripts/jarvis_weekly_review_314.py",
        ],
        timeout=180,
    )
    ai_adds: list[str] = []
    cur = ""
    for ln in diff.splitlines():
        if ln.startswith("COMMIT "):
            cur = ln.split()[1]
        elif ln.startswith("+") and not ln.startswith("+++") and AI_CALL_RE.search(ln):
            ai_adds.append(f"{cur}: {ln[1:].strip()[:100]}")
    return {"count": len(lines), "subjects": lines[:60], "ai_call_adds": ai_adds[:20]}


def collect_gha(since: datetime) -> dict[str, Any]:
    raw = _run(
        [
            "gh", "run", "list", "--limit", "400",
            "--created", f">={since.date().isoformat()}",
            "--json", "workflowName,conclusion,createdAt,event,databaseId",
        ],
        timeout=120,
    )
    runs = json.loads(raw or "[]")
    wf_paths = {
        str(w.get("name")): Path(str(w.get("path") or "")).name
        for w in json.loads(_run(["gh", "workflow", "list", "--all", "--json", "name,path"]) or "[]")
    }
    crons = workflow_crons()
    fails: Counter[str] = Counter()
    fail_ids: dict[str, int] = {}
    delays: dict[str, list[float]] = {}
    for r in runs:
        name = str(r.get("workflowName") or "")
        if r.get("conclusion") == "failure":
            fails[name] += 1
            fail_ids.setdefault(name, int(r.get("databaseId") or 0))
        wf_file = wf_paths.get(name, "")
        if r.get("event") == "schedule" and wf_file in crons:
            created = datetime.fromisoformat(str(r["createdAt"]).replace("Z", "+00:00"))
            d = schedule_delay_min(crons[wf_file], created)
            if d is not None:
                delays.setdefault(wf_file, []).append(d)
    delay_rows = []
    for wf, ds in sorted(delays.items()):
        ds.sort()
        delay_rows.append(
            {"workflow": wf, "runs": len(ds), "median_min": round(ds[len(ds) // 2]), "max_min": round(ds[-1])}
        )
    return {
        "runs": len(runs),
        "failures": [
            {"workflow": k, "count": v, "sample_run_id": fail_ids.get(k)}
            for k, v in fails.most_common()
        ],
        "schedule_delay": delay_rows,
    }


def _normalize(line: str) -> str:
    s = re.sub(r"\d{4}-\d\d-\d\d[T ][\d:.+Z-]*", "<ts>", line.strip())
    s = re.sub(r"\b[0-9a-f]{12,}\b|\b[0-9A-Za-z]{16}\b", "<id>", s)
    s = re.sub(r"\d+(\.\d+)?", "N", s)
    return s[:160]


def collect_launchd_logs(since: datetime) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not LOG_ROOT.is_dir():
        return rows
    cutoff = since.timestamp()
    for d in sorted(LOG_ROOT.glob("jarvis_*")):
        if not d.is_dir():
            continue
        counter: Counter[str] = Counter()
        for f in d.rglob("*.log"):
            try:
                if f.stat().st_mtime < cutoff:
                    continue
                # 大きいログは末尾だけ（週の分には十分）
                with f.open("rb") as fh:
                    fh.seek(0, 2)
                    fh.seek(max(0, fh.tell() - 2_000_000))
                    text = fh.read().decode("utf-8", errors="replace")
            except OSError:
                continue
            for ln in text.splitlines():
                # Traceback／raise 行は本体のエラー行と重複するので数えない
                if re.match(r"\s*(Traceback|raise |File \")", ln):
                    continue
                if ERROR_RE.search(ZERO_COUNT_RE.sub("", ln)):
                    counter[_normalize(ln)] += 1
        top = [(msg, n) for msg, n in counter.most_common(3) if n >= REPEAT_FLAG]
        if top:
            rows.append({"dir": d.name, "repeated": [{"msg": m, "count": n} for m, n in top]})
    return rows


def collect_tests() -> dict[str, Any]:
    results = []
    for t in sorted((REPO / "scripts" / "tests").glob("test_*.py")):
        r = subprocess.run(
            [sys.executable, "-m", "unittest", str(t)],
            cwd=str(REPO), capture_output=True, text=True, timeout=300,
        )
        tail = (r.stderr or r.stdout).strip().splitlines()[-1:] or [""]
        results.append({"file": t.name, "ok": r.returncode == 0, "tail": tail[0][:120]})
    return {"total": len(results), "failed": [x for x in results if not x["ok"]]}


def collect_workflow_deps() -> list[str]:
    """workflow が呼ぶ scripts の import に対して pip 導入が足りないもの。"""

    def local_imports(f: Path, seen: set[Path]) -> None:
        if f in seen or not f.exists():
            return
        seen.add(f)
        for m in re.finditer(
            r"^\s*(?:from|import)\s+([A-Za-z_]\w*)", f.read_text(errors="ignore"), re.M
        ):
            cand = REPO / "scripts" / f"{m.group(1)}.py"
            if cand.exists():
                local_imports(cand, seen)

    missing = []
    for wf in sorted((REPO / ".github" / "workflows").glob("*.yml")):
        s = wf.read_text(encoding="utf-8")
        scripts = set(re.findall(r"scripts/(\w+\.py)", s))
        if not scripts:
            continue
        seen: set[Path] = set()
        for sc in scripts:
            local_imports(REPO / "scripts" / sc, seen)
        need = set()
        for f in seen:
            t = f.read_text(errors="ignore")
            if re.search(r"^\s*(import|from) yaml", t, re.M):
                need.add("pyyaml")
            if re.search(r"^\s*(import|from) requests", t, re.M):
                need.add("requests")
        have = set()
        if re.search(r"pyyaml|PyYAML|requirements", s):
            have.add("pyyaml")
        if re.search(r"requests|requirements", s):
            have.add("requests")
        for pkg in sorted(need - have):
            missing.append(f"{wf.name}: {pkg}")
    return missing


# ---- 出力 --------------------------------------------------------------------


def build_flags(facts: dict[str, Any]) -> list[str]:
    flags: list[str] = []
    for f in facts["gha"]["failures"]:
        flags.append(f"GHA 失敗: {f['workflow']} ×{f['count']}（run {f['sample_run_id']}）")
    late = [d for d in facts["gha"]["schedule_delay"] if d["median_min"] >= DELAY_FLAG_MIN]
    if late:
        worst = max(late, key=lambda d: d["median_min"])
        flags.append(
            f"時刻ずれ: {len(late)} 本が中央値 {DELAY_FLAG_MIN} 分以上遅れ"
            f"（最悪 {worst['workflow']} 中央値 {worst['median_min']} 分）"
        )
    for row in facts["launchd"]:
        # 1 系統 1 行（最多のエラー文）。全文は latest.json
        r = row["repeated"][0]
        flags.append(f"繰り返しエラー: {row['dir']} ×{r['count']} — {r['msg'][:80]}")
    for t in facts["tests"]["failed"]:
        flags.append(f"テスト失敗: {t['file']} — {t['tail']}")
    for m in facts["deps_missing"]:
        flags.append(f"依存不足: {m}")
    per_commit = Counter(a.split(":", 1)[0] for a in facts["commits"]["ai_call_adds"])
    for sha, n in per_commit.items():
        flags.append(f"AI 呼び出し追加: {sha}（{n}行。常時 ON か・回数上限があるか要確認）")
    return flags


def render_md(facts: dict[str, Any]) -> str:
    c, g = facts["commits"], facts["gha"]
    lines = [
        f"# 314 週次 機械チェック {facts['date']}",
        "",
        f"対象: {facts['since']} 〜 {facts['date']}（main）",
        "",
        f"## 要確認 {len(facts['flags'])} 件",
        "",
    ]
    lines += [f"- {x}" for x in facts["flags"]] or ["- なし"]
    lines += ["", f"## コミット {c['count']} 件", ""]
    lines += [f"- {s}" for s in c["subjects"]]
    lines += ["", f"## GHA 実行 {g['runs']} 件・時刻ずれ（分）", ""]
    lines += [
        f"- {d['workflow']}: 中央値 {d['median_min']} / 最大 {d['max_min']}（{d['runs']}回）"
        for d in g["schedule_delay"]
    ]
    lines += ["", f"## テスト {facts['tests']['total']} 本・失敗 {len(facts['tests']['failed'])}", ""]
    return "\n".join(lines) + "\n"


def slack_text(facts: dict[str, Any]) -> str:
    n = len(facts["flags"])
    head = "【ops】314 業務品質監査・週次" if n else "【報告】314 業務品質監査・週次"
    body = [head, f"コミット{facts['commits']['count']}件／要確認{n}件"]
    body += [f"・{x[:60]}" for x in facts["flags"][:5]]
    if n > 5:
        body.append(f"・ほか{n - 5}件")
    body.append("判断と修正は 9:30 の Claude 点検 → PR")
    return "\n".join(body)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--dry-run", action="store_true", help="書き出しのみ。Slack なし")
    ap.add_argument("--post", action="store_true", help="Slack（要確認あり #ops／なし #report）")
    args = ap.parse_args()

    if (os.environ.get("JARVIS_WEEKLY_REVIEW_314_DISABLE") or "").strip() in ("1", "true"):
        print(f"{LOG}: disabled")
        return 0

    now = datetime.now(JST)
    since = now - timedelta(days=args.days)
    try:
        _run(["git", "fetch", "--quiet", "origin", "main"])
    except Exception as exc:
        print(f"{LOG}: git fetch FAIL（ローカルの origin/main で続行）: {exc}", file=sys.stderr)

    facts: dict[str, Any] = {"date": now.strftime("%Y-%m-%d"), "since": since.strftime("%Y-%m-%d")}
    for key, fn in (
        ("commits", lambda: collect_commits(since)),
        ("gha", lambda: collect_gha(since)),
        ("launchd", lambda: collect_launchd_logs(since)),
        ("tests", collect_tests),
        ("deps_missing", collect_workflow_deps),
    ):
        try:
            facts[key] = fn()
        except Exception as exc:
            print(f"{LOG}: {key} FAIL: {exc}", file=sys.stderr)
            facts[key] = {"error": str(exc)}
    # 収集失敗も要確認に載せる
    for key in ("commits", "gha", "tests"):
        if isinstance(facts[key], dict) and "error" in facts[key]:
            facts[key] = {
                "count": 0, "subjects": [], "ai_call_adds": [], "runs": 0,
                "failures": [], "schedule_delay": [], "total": 0, "failed": [],
                "error": facts[key]["error"],
            }
    if isinstance(facts["launchd"], dict):
        facts["launchd"] = []
    if isinstance(facts["deps_missing"], dict):
        facts["deps_missing"] = []
    facts["flags"] = build_flags(facts)
    for key in ("commits", "gha", "tests"):
        if facts[key].get("error"):
            facts["flags"].append(f"収集失敗: {key} — {facts[key]['error'][:80]}")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    md = render_md(facts)
    stamp = now.strftime("%Y%m%d")
    (OUT_DIR / f"facts_{stamp}.md").write_text(md, encoding="utf-8")
    (OUT_DIR / "latest.json").write_text(
        json.dumps(facts, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(md)
    print(f"{LOG}: wrote {OUT_DIR}/facts_{stamp}.md flags={len(facts['flags'])}")

    if args.post and not args.dry_run:
        ch = "ops" if facts["flags"] else "report"
        r = subprocess.run(
            [
                sys.executable, str(REPO / "scripts" / "jarvis_slack_webhook_post.py"),
                "--channel", ch, "--username", "314 業務品質監査", "--text", slack_text(facts),
            ],
            cwd=str(REPO), timeout=60,
        )
        if r.returncode != 0:
            print(f"{LOG}: slack FAIL rc={r.returncode}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
