#!/usr/bin/env python3
"""315-B 300番台 停止・空回り監視（日次・AI なし）。

FlowForge 315-B（flow_ZQIfYZY4GJF2XspXY8i0sGWD）の工程をそのまま関数にしている:
  ① 監視基準を取得      fetch_criteria   … config/freshness_slo.yaml の stall_watch_315b（読めなければ全体の異常）
  ② 監視データを検証    validate_data    … 成果物・ログ・状態ファイルの有無と形式。欠けた対象に印
  ③ 停止を判定          judge_stop       … 最終成功（311 は定時実行の生存）と上限の比較
  ④ 空回りを判定        judge_idle       … 311 同じ下書き 4 回／1 時間、313 同じ候補 3 回連続・進展なし、317 は枠だけ
  ⑤ 状態変化を判定      judge_state_change … 正常／遅れ／空回り／読取不可、前回の通知済みと比べて 新規・回復・継続
  ⑥ 監視結果・通知状態を保存 save_state  … .jarvis_state/stall_watch_315b.json（通知待ちを先に残す）
  ⑦ Jarvis ダッシュボードへ反映 push_dashboard … sync_meta.stall_watch_315b（/agent-team「週次稼働」タブが読む）
  ⑧ Slack #ops へ通知・終了 post_ops    … 異常の発生・回復のときだけ。失敗したら通知済みにせず次回再送

    ~/selenium_env/venv/bin/python scripts/jarvis_stall_watch_315b.py --dry-run
    ~/selenium_env/venv/bin/python scripts/jarvis_stall_watch_315b.py --post

入口: 既存の鮮度監視の launchd（毎日 08:20・18:20、launchd/freshness_watch_runner.sh）に相乗り
結果: 成功 0 ／ 部分成功 2（一部読めない・画面反映や通知の失敗）／ 失敗 1（基準の読取・結果の保存の失敗）
停止: JARVIS_STALL_WATCH_315B_DISABLE=1
やらない: 自動復旧・Backlog 起票・AI 分析・途中の人の承認
"""
from __future__ import annotations

import argparse
import glob
import hashlib
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
import jarvis_freshness_watch as fw  # noqa: E402

REPO = fw.REPO
CONFIG = fw.CONFIG
STATE = REPO / ".jarvis_state" / "stall_watch_315b.json"
SECTION = "stall_watch_315b"
SYNC_KEY = "stall_watch_315b"
JST = fw.JST
LOG = "📎 315-B 停止・空回り監視"
MONITOR_ID = "_monitor"

STATUS_LABEL = {"ok": "正常", "stale": "遅れ", "idle": "空回り", "unknown": "読取不可"}
# 同時に当てはまるときの優先（読めないものは他の判定より先に出す）
STATUS_RANK = {"unknown": 3, "stale": 2, "idle": 1, "ok": 0}


class CriteriaError(Exception):
    """監視基準が読めない・形が違う（全体の異常として扱う）。"""


# ---------- ① 監視基準を取得 ----------

def _abs(repo: Path, p: str) -> Path:
    path = Path(os.path.expanduser(str(p)))
    return path if path.is_absolute() else repo / path


def fetch_criteria(config_path: Path = CONFIG) -> dict[str, Any]:
    try:
        cfg = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as exc:
        raise CriteriaError(f"設定ファイルを読めない: {type(exc).__name__}") from exc
    if not isinstance(cfg, dict):
        raise CriteriaError("設定ファイルの形が違う")
    sec = cfg.get(SECTION)
    if not isinstance(sec, dict):
        raise CriteriaError(f"{SECTION} の節がない")
    targets = sec.get("targets")
    if not isinstance(targets, list) or not targets:
        raise CriteriaError("監視対象（targets）が空")
    products = {p.get("id"): p for p in (cfg.get("products") or []) if isinstance(p, dict)}
    out = []
    seen: set[str] = set()
    for t in targets:
        if not isinstance(t, dict):
            raise CriteriaError("監視対象の形が違う")
        tid = str(t.get("id") or "")
        for k in ("id", "label", "owner", "action", "stop"):
            if not t.get(k):
                raise CriteriaError(f"{tid or '?'}: {k} がない")
        if tid in seen:
            raise CriteriaError(f"{tid}: 重複")
        seen.add(tid)
        stop = dict(t["stop"])
        if stop.get("ref"):
            # 既存の鮮度監視の設定をそのまま使う（314 = weekly_review_facts）
            ref = products.get(stop["ref"])
            if not ref:
                raise CriteriaError(f"{tid}: 参照先 {stop['ref']} が products にない")
            stop = {**{k: v for k, v in ref.items() if k in ("kind", "glob", "file", "path", "workflow", "max_age_h", "title_contains")}, "ref": stop["ref"]}
        if not stop.get("kind") or stop.get("max_age_h") in (None, ""):
            raise CriteriaError(f"{tid}: stop.kind／max_age_h がない")
        try:
            stop["max_age_h"] = float(stop["max_age_h"])
        except (TypeError, ValueError) as exc:
            raise CriteriaError(f"{tid}: max_age_h が数でない") from exc
        idle = t.get("idle")
        if idle is not None and (not isinstance(idle, dict) or not idle.get("kind")):
            raise CriteriaError(f"{tid}: idle の形が違う")
        out.append({**t, "id": tid, "stop": stop, "idle": idle})
    return {"targets": out}


# ---------- ② 監視データを検証 ----------

def _paths_of(spec: dict[str, Any], repo: Path) -> list[tuple[str, Path | str]]:
    """(形式, パス or glob) の一覧。gha は手元にファイルがないので対象外。"""
    kind = spec.get("kind")
    if kind in ("json_time",):
        return [("json", _abs(repo, spec["file"]))]
    if kind in ("file_mtime", "log_last_match"):
        return [("glob", str(_abs(repo, spec["glob"])))]
    if kind == "gate_draft_repeat":
        return [("dir", _abs(repo, spec["dir"]))]
    if kind == "candidate_repeat":
        return [("json", _abs(repo, spec["file"]))] + (
            [("json?", _abs(repo, spec["extra_file"]))] if spec.get("extra_file") else []
        )
    return []


def validate_data(targets: list[dict[str, Any]], repo: Path = REPO) -> dict[str, list[str]]:
    """対象ごとの欠損・形式不整合（空リストなら問題なし）。"""
    flags: dict[str, list[str]] = {}
    for t in targets:
        bad: list[str] = []
        for part, spec in (("停止", t["stop"]), ("空回り", t.get("idle") or {})):
            for fmt, p in _paths_of(spec, repo):
                if fmt == "glob":
                    if not glob.glob(str(p)):
                        bad.append(f"{part}: ファイルなし")
                elif fmt == "dir":
                    if not Path(p).is_dir():
                        bad.append(f"{part}: フォルダなし")
                elif fmt in ("json", "json?"):
                    path = Path(p)
                    if not path.is_file():
                        if fmt == "json":
                            bad.append(f"{part}: ファイルなし")
                        continue
                    try:
                        json.loads(path.read_text(encoding="utf-8"))
                    except (OSError, ValueError):
                        bad.append(f"{part}: JSON を読めない")
        flags[t["id"]] = bad
    return flags


# ---------- ③ 停止を判定 ----------

def _log_last_match(spec: dict[str, Any], repo: Path) -> tuple[datetime | None, str]:
    """ログ末尾から pattern の最後の時刻（311 の定時実行の見出し）。"""
    files = glob.glob(str(_abs(repo, spec["glob"])))
    if not files:
        return None, "ファイルなし"
    rx = re.compile(str(spec["pattern"]))
    fmt = str(spec.get("time_format") or "%Y-%m-%d %H:%M:%S")
    tail_bytes = int(spec.get("tail_bytes") or 65536)
    best: datetime | None = None
    for f in files:
        with open(f, "rb") as fh:
            fh.seek(0, os.SEEK_END)
            size = fh.tell()
            fh.seek(max(0, size - tail_bytes))
            text = fh.read().decode("utf-8", errors="replace")
        for m in rx.finditer(text):
            try:
                t = datetime.strptime(m.group(1), fmt).replace(tzinfo=JST)
            except ValueError:
                continue
            if best is None or t > best:
                best = t
    return (best, "") if best else (None, "実行の記録なし")


def _gha_last_titled(spec: dict[str, Any], repo: Path) -> tuple[datetime | None, str]:
    """gha で title_contains があるとき、その文字を title に含む成功実行の最新時刻。
    312 は collect と reflect が同じ workflow なので、run-name で見分けた collect だけを数える。"""
    needle = str(spec["title_contains"])
    r = subprocess.run(
        ["gh", "run", "list", "-w", str(spec["workflow"]), "-s", "success", "-L", "100",
         "--json", "updatedAt,displayTitle"],
        capture_output=True, text=True, timeout=60, cwd=repo,
    )
    if r.returncode != 0:
        return None, f"gh 失敗: {r.stderr.strip()[:80]}"
    try:
        runs = json.loads(r.stdout or "[]")
    except ValueError:
        return None, "gh の出力を読めない"
    times = [fw._parse_ts(x.get("updatedAt")) for x in runs if needle in str(x.get("displayTitle") or "")]
    times = [t for t in times if t]
    return (max(times), "") if times else (None, f"成功履歴なし（title に「{needle}」を含む実行）")


def last_success(spec: dict[str, Any], *, repo: Path = REPO) -> tuple[datetime | None, str]:
    if spec.get("kind") == "log_last_match":
        return _log_last_match(spec, repo)
    if spec.get("kind") == "gha" and spec.get("title_contains"):
        return _gha_last_titled(spec, repo)
    return fw.last_time(spec, repo=repo)


def judge_stop(t: dict[str, Any], now: datetime, getter: Callable = last_success) -> dict[str, Any]:
    spec = t["stop"]
    try:
        last, why = getter(spec)
    except (OSError, subprocess.SubprocessError, ValueError, KeyError) as exc:
        last, why = None, f"確認不能: {type(exc).__name__}"
    if last is None:
        return {"status": "unknown", "last": None, "age_h": None, "max_age_h": spec["max_age_h"], "why": why or "時刻なし"}
    age_h = (now - last).total_seconds() / 3600
    stale = age_h > spec["max_age_h"]
    return {
        "status": "stale" if stale else "ok",
        "last": last.isoformat(),
        "age_h": round(age_h, 2),
        "max_age_h": spec["max_age_h"],
        "why": f"最終成功 {_age_text(age_h)}（上限 {spec['max_age_h']:g}h）",
    }


# ---------- ④ 空回りを判定 ----------

_GATE_RE = re.compile(r"gate_(\d{8}_\d{6})\.json$")


def idle_311(spec: dict[str, Any], now: datetime, repo: Path = REPO) -> dict[str, Any]:
    """同じ下書き（draft_path）が window_min 分の中で threshold 回以上判定されたら空回り。"""
    d = _abs(repo, spec["dir"])
    if not d.is_dir():
        return {"status": "unknown", "why": "判定結果のフォルダなし"}
    threshold = int(spec.get("threshold") or 4)
    window = timedelta(minutes=float(spec.get("window_min") or 60))
    since = now - timedelta(hours=float(spec.get("lookback_h") or 14))
    by_draft: dict[str, list[datetime]] = {}
    unreadable = 0
    for f in d.glob("gate_*.json"):
        m = _GATE_RE.search(f.name)
        if not m:
            continue
        try:
            at = datetime.strptime(m.group(1), "%Y%m%d_%H%M%S").replace(tzinfo=JST)
        except ValueError:
            continue
        if at < since or at > now + timedelta(minutes=5):
            continue
        try:
            draft = str(json.loads(f.read_text(encoding="utf-8")).get("draft_path") or "")
        except (OSError, ValueError, AttributeError):
            unreadable += 1
            continue
        if draft:
            by_draft.setdefault(draft, []).append(at)
    worst: tuple[int, str, datetime] | None = None
    for draft, times in by_draft.items():
        times.sort()
        j = 0
        for i, t in enumerate(times):
            while times[i] - times[j] > window:
                j += 1
            n = i - j + 1
            if n >= threshold and (worst is None or n > worst[0]):
                worst = (n, draft, t)
    note = f"（読めない判定結果 {unreadable} 件）" if unreadable else ""
    if worst:
        n, draft, t = worst
        return {
            "status": "idle",
            "why": f"同じ下書き {_short_path(draft)} を {window.total_seconds() / 60:.0f} 分で {n} 回判定（{t.astimezone(JST):%m/%d %H:%M} まで）{note}",
            "detail": {"draft": _short_path(draft), "count": n, "last_at": t.isoformat()},
        }
    return {"status": "ok", "why": f"反復なし{note}", "unreadable": unreadable}


def _ids(rows: Any, key: str = "task_id") -> list[str]:
    if not isinstance(rows, list):
        return []
    return sorted({str(r.get(key)) for r in rows if isinstance(r, dict) and r.get(key)})


def idle_313(spec: dict[str, Any], history: list[dict[str, Any]], repo: Path = REPO) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """同じ候補の集合が runs 回連続し、進展（超過件数の減少）がなければ空回り。

    313 は 1 日 1 回（20:00）なので、313 の実行ごと（file の at）に 1 件だけ履歴へ足す。
    片付け（extra_file）は同じ回に書かれたもの（at が近い）だけ候補に含める。超過 0 件の日は書かれない。
    """
    try:
        main = json.loads(_abs(repo, spec["file"]).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return {"status": "unknown", "why": f"候補を読めない: {type(exc).__name__}"}, history
    run_at = fw._parse_ts(main.get("at"))
    if run_at is None:
        return {"status": "unknown", "why": "候補の時刻なし"}, history
    cand = _ids(main.get("candidates"))
    extra_ids: list[str] = []
    total = None
    if spec.get("extra_file"):
        try:
            extra = json.loads(_abs(repo, spec["extra_file"]).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            extra = {}
        ex_at = fw._parse_ts(extra.get("at")) if isinstance(extra, dict) else None
        if ex_at and abs((run_at - ex_at).total_seconds()) <= float(spec.get("same_run_within_min") or 120) * 60:
            extra_ids = _ids(extra.get("items"))
            total = extra.get("total")
    ids = sorted(set(cand) | set(extra_ids))
    fp = hashlib.sha256("\n".join(ids).encode("utf-8")).hexdigest()[:16]
    entry = {"run_at": run_at.isoformat(), "fp": fp, "n": len(ids), "total": total}
    hist = [h for h in history if isinstance(h, dict) and h.get("run_at")]
    if not hist or hist[-1]["run_at"] != entry["run_at"]:
        hist.append(entry)
    hist = hist[-int(spec.get("keep") or 10):]
    runs = int(spec.get("runs") or 3)
    last = hist[-runs:]
    if len(last) < runs:
        return {"status": "ok", "why": f"履歴 {len(last)}/{runs} 回（判定前）"}, hist
    same = len({h["fp"] for h in last}) == 1 and last[-1]["n"] > 0
    totals = [h.get("total") for h in last]
    progressed = all(isinstance(x, (int, float)) for x in totals) and any(
        totals[i] < totals[i - 1] for i in range(1, len(totals))
    )
    if same and not progressed:
        return {
            "status": "idle",
            "why": f"同じ候補 {last[-1]['n']} 件が {runs} 回連続・進展なし",
            "detail": {"n": last[-1]["n"], "runs": runs, "since": last[0]["run_at"]},
        }, hist
    return {"status": "ok", "why": "候補が動いている" if not same else "超過が減っている"}, hist


def judge_idle(t: dict[str, Any], now: datetime, history: dict[str, Any], repo: Path = REPO) -> tuple[dict[str, Any], dict[str, Any]]:
    spec = t.get("idle")
    if not spec or spec.get("kind") == "skip":
        return {"status": "skip", "why": (spec or {}).get("note") or "空回り判定なし"}, history
    try:
        if spec["kind"] == "gate_draft_repeat":
            return idle_311(spec, now, repo), history
        if spec["kind"] == "candidate_repeat":
            res, hist = idle_313(spec, list(history.get(t["id"]) or []), repo)
            return res, {**history, t["id"]: hist}
    except (OSError, ValueError, KeyError) as exc:
        return {"status": "unknown", "why": f"空回り確認不能: {type(exc).__name__}"}, history
    return {"status": "unknown", "why": f"未知の空回り判定: {spec['kind']}"}, history


# ---------- ⑤ 状態変化を判定 ----------

def classify(stop: dict[str, Any], idle: dict[str, Any], missing: list[str]) -> tuple[str, str]:
    cands = [(stop["status"], stop.get("why") or "")]
    if idle.get("status") in ("idle", "unknown"):
        cands.append((idle["status"], idle.get("why") or ""))
    if missing:
        cands.append(("unknown", "・".join(missing)))
    status, why = max(cands, key=lambda c: STATUS_RANK[c[0]])
    return status, why


def judge_state_change(rows: list[dict[str, Any]], notified: dict[str, Any]) -> list[dict[str, Any]]:
    """通知済みの状態（notified）と今回を比べ、通知すべき変化だけ返す。

    新規: 今回異常で、通知済みが正常または別の異常／回復: 通知済みが異常で今回正常／継続: 同じ異常（出さない）
    """
    out = []
    for r in rows:
        prev = (notified.get(r["id"]) or {}).get("status", "ok")
        cur = r["status"]
        if cur == prev:
            continue
        kind = "recovered" if cur == "ok" else "new"
        out.append({"id": r["id"], "kind": kind, "from": prev, "to": cur})
    return out


# ---------- 通知文（iPhone 前提: 番号＋短い役割語、1 項目 2 行まで） ----------

def _age_text(h: float) -> str:
    return f"{h / 24:.1f}日前" if h >= 48 else (f"{h:.0f}時間前" if h >= 1 else f"{h * 60:.0f}分前")


def _short_path(p: str) -> str:
    parts = Path(p).parts
    return "/".join(parts[-2:]) if len(parts) >= 2 else p


def build_message(changes: list[dict[str, Any]], rows: dict[str, dict[str, Any]]) -> str:
    lines = ["【ops】315-B 停止・空回り監視"]
    for c in changes:
        r = rows[c["id"]]
        if c["kind"] == "recovered":
            lines.append(f"🟢 回復 {r['label']}（{STATUS_LABEL.get(c['from'], c['from'])}→正常）")
            continue
        mark = "🟡" if c["to"] == "unknown" else "🔴"
        lines.append(f"{mark} {r['label']}: {STATUS_LABEL[c['to']]} — {r['why']}")
        lines.append(f"　担当 {r['owner']}／まず: {r['action']}")
    return "\n".join(lines)


# ---------- ⑥〜⑧ 保存・画面反映・通知 ----------

def load_prev(path: Path) -> tuple[dict[str, Any], str]:
    if not path.is_file():
        return {}, ""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return (data if isinstance(data, dict) else {}), ("" if isinstance(data, dict) else "前回状態の形が違う")
    except (OSError, ValueError) as exc:
        # 読めないときは「通知済みなし」として扱う（取りこぼすより重複を選ぶ）。部分成功にする
        return {}, f"前回状態を読めない: {type(exc).__name__}"


def save_state(path: Path, state: dict[str, Any]) -> tuple[bool, str]:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        tmp.replace(path)
        return True, ""
    except OSError as exc:
        return False, f"保存できない: {type(exc).__name__}"


def push_dashboard(payload: dict[str, Any]) -> tuple[bool, str]:
    url = (os.environ.get("JARVIS_SUPABASE_URL") or "").strip()
    key = (os.environ.get("JARVIS_SUPABASE_SERVICE_ROLE_KEY") or "").strip()
    if not url or not key:
        return False, "JARVIS_SUPABASE_* 未設定"
    try:
        from supabase import create_client

        sb = create_client(url, key)
        sb.table("sync_meta").upsert(
            {"key": SYNC_KEY, "value": json.dumps(payload, ensure_ascii=False), "updated_at": payload["checked_at"]},
            on_conflict="key",
        ).execute()
        return True, ""
    except Exception as exc:  # noqa: BLE001 — 本文に秘密が混ざりうるので型名だけ
        return False, f"反映できない: {type(exc).__name__}"


def post_ops(text: str) -> tuple[bool, str]:
    r = subprocess.run(
        [sys.executable, str(REPO / "scripts" / "jarvis_slack_webhook_post.py"), "--channel", "ops", "--text", text],
        cwd=REPO,
        capture_output=True,
        text=True,
        timeout=60,
    )
    return (r.returncode == 0), ("" if r.returncode == 0 else f"投稿失敗 rc={r.returncode}")


def dashboard_payload(state: dict[str, Any]) -> dict[str, Any]:
    keep = ("id", "label", "owner", "status", "why", "last", "age_h", "max_age_h", "stop_status", "idle_status", "idle_why", "missing")
    return {
        "run_id": state["run_id"],
        "checked_at": state["checked_at"],
        "result": state["result"],
        "result_why": state.get("result_why", []),
        "save": state.get("save"),
        "rows": [{k: r.get(k) for k in keep} for r in state.get("rows", [])],
        "notified": state.get("notified", {}),
        "pending": state.get("pending", []),
    }


def run(
    now: datetime,
    *,
    config_path: Path = CONFIG,
    state_path: Path = STATE,
    repo: Path = REPO,
    getter: Callable | None = None,
    pusher: Callable[[dict[str, Any]], tuple[bool, str]] = push_dashboard,
    poster: Callable[[str], tuple[bool, str]] | None = post_ops,
    dry_run: bool = False,
    out: Callable[[str], None] = print,
) -> tuple[int, dict[str, Any]]:
    getter = getter or (lambda spec: last_success(spec, repo=repo))
    run_id = f"315b-{now.astimezone(JST):%Y%m%d-%H%M%S}"
    prev, prev_err = load_prev(state_path)
    notified: dict[str, Any] = dict(prev.get("notified") or {})
    history: dict[str, Any] = dict(prev.get("idle_history") or {})
    result_why: list[str] = [prev_err] if prev_err else []

    # ①
    criteria_err = ""
    try:
        targets = fetch_criteria(config_path)["targets"]
    except CriteriaError as exc:
        targets, criteria_err = [], str(exc)
        result_why.append(f"監視基準の読取失敗: {exc}")

    rows: list[dict[str, Any]] = []
    if targets:
        flags = validate_data(targets, repo)  # ②
        for t in targets:
            stop = judge_stop(t, now, getter)  # ③
            idle, history = judge_idle(t, now, history, repo)  # ④
            status, why = classify(stop, idle, flags[t["id"]])  # ⑤（分類）
            rows.append({
                "id": t["id"], "label": t["label"], "owner": t["owner"], "action": t["action"],
                "status": status, "why": why,
                "last": stop["last"], "age_h": stop["age_h"], "max_age_h": stop["max_age_h"],
                "stop_status": stop["status"], "idle_status": idle["status"], "idle_why": idle.get("why"),
                "missing": flags[t["id"]],
            })
    monitor_row = {
        "id": MONITOR_ID, "label": "315-B 監視そのもの", "owner": "315 連携健全性点検",
        "action": "config/freshness_slo.yaml の stall_watch_315b と保存先を確認",
        "status": "unknown" if criteria_err else "ok", "why": criteria_err or "基準を読めた",
    }
    # 基準が読めないときは対象の通知済み状態に触らない（回復と誤報しない）
    judged = rows + [monitor_row]
    changes = judge_state_change(judged, notified)
    by_id = {r["id"]: r for r in judged}

    for r in rows:
        out(f"{r['status'].upper():7} {r['id']:4} {r['label']:<16} {r['why']}")
    if criteria_err:
        out(f"UNKNOWN 監視基準: {criteria_err}")

    result = "failure" if criteria_err else ("partial" if any(r["status"] == "unknown" for r in rows) or prev_err else "success")
    state: dict[str, Any] = {
        "run_id": run_id,
        "checked_at": now.astimezone(JST).isoformat(timespec="seconds"),
        "result": result,
        "result_why": result_why,
        "rows": rows,
        "notified": notified,
        "pending": changes,
        "idle_history": history,
        "save": None,
        "dashboard": prev.get("dashboard"),
        "notify": None,
    }
    if dry_run:
        if changes:
            out("--- 投稿予定 ---\n" + build_message(changes, by_id))
        out(f"{LOG}: dry-run result={result}（保存・画面反映・通知なし）")
        return 0, state

    # ⑥ 通知待ちを先に保存（通知前に落ちても次回に引き継ぐ）
    ok, why = save_state(state_path, state)
    state["save"] = {"ok": ok, "at": state["checked_at"], "why": why}
    if not ok:
        result_why.append(f"結果の保存失敗: {why}")
        by_id[MONITOR_ID] = {**monitor_row, "status": "unknown", "why": criteria_err or "結果の保存に失敗"}
        # 「監視そのもの」の変化は保存失敗を反映して計算し直す（回復と誤報しない）
        changes = [c for c in changes if c["id"] != MONITOR_ID]
        prev_m = (notified.get(MONITOR_ID) or {}).get("status", "ok")
        if prev_m != "unknown":
            changes.append({"id": MONITOR_ID, "kind": "new", "from": prev_m, "to": "unknown"})

    # ⑦ 画面反映（保存とは別に成否を記録）
    try:
        d_ok, d_why = pusher(dashboard_payload(state))
    except Exception as exc:  # noqa: BLE001
        d_ok, d_why = False, f"反映できない: {type(exc).__name__}"
    state["dashboard"] = {"ok": d_ok, "at": state["checked_at"], "why": d_why, "run_id": run_id}
    if not d_ok:
        result_why.append(f"画面反映の失敗: {d_why}")

    # ⑧ 異常の発生・回復のときだけ #ops。失敗したら通知済みにしない（次回の再送対象）
    notify = {"needed": bool(changes), "ok": None, "why": "", "ids": [c["id"] for c in changes]}
    if changes:
        if poster is None:
            notify.update(ok=False, why="投稿しない設定（--post なし）")
        else:
            try:
                p_ok, p_why = poster(build_message(changes, by_id))
            except (OSError, subprocess.SubprocessError) as exc:
                p_ok, p_why = False, f"投稿失敗: {type(exc).__name__}"
            notify.update(ok=p_ok, why=p_why)
            if p_ok:
                at = state["checked_at"]
                for c in changes:
                    notified[c["id"]] = {"status": c["to"], "at": at, "run_id": run_id}
                state["pending"] = []
        if not notify["ok"]:
            result_why.append(f"通知の失敗・保留: {notify['why']}")
    state["notify"] = notify
    state["notified"] = notified

    if result == "success" and (not ok or not d_ok or (changes and not notify["ok"])):
        result = "partial"
    if not ok:
        result = "failure"
    state["result"] = result
    state["result_why"] = result_why
    ok2, why2 = save_state(state_path, state)
    if not ok2:
        state["result"] = result = "failure"
        result_why.append(f"最終保存の失敗: {why2}")
    out(f"{LOG}: result={result} save={'ok' if ok else 'NG'} dashboard={'ok' if d_ok else 'NG'} notify={notify['ok'] if changes else '不要'} run_id={run_id}")
    for w in result_why:
        out(f"  - {w}")
    return {"success": 0, "partial": 2, "failure": 1}[result], state


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true", help="判定だけ（保存・画面反映・通知なし）")
    ap.add_argument("--post", action="store_true", help="#ops へ通知する（無ければ通知待ちのまま保存）")
    args = ap.parse_args()
    if os.environ.get("JARVIS_STALL_WATCH_315B_DISABLE") == "1":
        print(f"{LOG}: disabled")
        return 0
    rc, _ = run(
        datetime.now(timezone.utc),
        poster=post_ops if args.post else None,
        dry_run=args.dry_run,
    )
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
