#!/usr/bin/env python3
"""315 鮮度監視（デッドマンスイッチ）— 成果物が決めた時間より古くなったら #ops に 1 回だけ出す（AI なし）。

エラーを探すのではなく「成功が届いていない」ことを見る。止まって何も出ない静かな失敗
（オプチャのスレッドが 3 週間 0 件など）を拾うため。対象と閾値は config/freshness_slo.yaml。

    ~/selenium_env/venv/bin/python scripts/jarvis_freshness_watch.py --dry-run
    ~/selenium_env/venv/bin/python scripts/jarvis_freshness_watch.py --post

通知: 新しく古くなった／回復した成果物があるときだけ（同じ状態が続く間は黙る）
入口: launchd 1 日 2 回（install_freshness_watch_launchd.sh）／週次 314 も結果を読む
状態: .jarvis_state/freshness_watch.json
停止: JARVIS_FRESHNESS_WATCH_DISABLE=1
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import yaml

REPO = Path(__file__).resolve().parents[1]
CONFIG = REPO / "config" / "freshness_slo.yaml"
STATE = REPO / ".jarvis_state" / "freshness_watch.json"
JST = ZoneInfo("Asia/Tokyo")
LOG = "📎 315 鮮度監視"


def _parse_ts(v: Any) -> datetime | None:
    if v in (None, ""):
        return None
    if isinstance(v, (int, float)):
        x = float(v)
        return datetime.fromtimestamp(x / 1000 if x > 1e12 else x, tz=timezone.utc)
    s = str(v).strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=JST)


def _walk(obj: Any, parts: list[str]) -> list[Any]:
    if not parts:
        return [obj]
    head, rest = parts[0], parts[1:]
    if head == "*":
        vals = obj.values() if isinstance(obj, dict) else (obj if isinstance(obj, list) else [])
        out: list[Any] = []
        for v in vals:
            out.extend(_walk(v, rest))
        return out
    if isinstance(obj, dict) and head in obj:
        return _walk(obj[head], rest)
    return []


def last_time(p: dict[str, Any], *, repo: Path = REPO) -> tuple[datetime | None, str]:
    """成果物の最終成功時刻と、取れなかった理由。"""
    kind = p.get("kind")
    if kind == "file_mtime":
        pat = os.path.expanduser(str(p["glob"]))
        if not os.path.isabs(pat):
            pat = str(repo / pat)
        files = glob.glob(pat)
        if not files:
            return None, "ファイルなし"
        return datetime.fromtimestamp(max(os.path.getmtime(f) for f in files), tz=timezone.utc), ""
    if kind == "json_time":
        f = repo / str(p["file"])
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            return None, f"読めない: {type(e).__name__}"
        ts = [t for t in (_parse_ts(v) for v in _walk(data, str(p["path"]).split("."))) if t]
        return (max(ts), "") if ts else (None, "時刻なし")
    if kind == "gha":
        r = subprocess.run(
            [
                "gh", "run", "list", "-w", str(p["workflow"]), "-s", "success", "-L", "1",
                "--json", "updatedAt", "--jq", ".[0].updatedAt // empty",
            ],
            capture_output=True, text=True, timeout=60, cwd=repo,
        )
        if r.returncode != 0:
            return None, f"gh 失敗: {r.stderr.strip()[:80]}"
        t = _parse_ts(r.stdout.strip())
        return (t, "") if t else (None, "成功履歴なし")
    return None, f"未知の kind: {kind}"


def evaluate(cfg: dict[str, Any], now: datetime, getter=last_time) -> list[dict[str, Any]]:
    rows = []
    for p in cfg.get("products") or []:
        if p.get("kind") == "connection_state":
            try:
                f = Path(str(p["file"])).expanduser()
                if not f.is_absolute():
                    f = REPO / f
                data = json.loads(f.read_text(encoding="utf-8"))
                matches = _walk(data, str(p["path"]).split("."))
                item = matches[0] if matches and isinstance(matches[0], dict) else {}
                t = _parse_ts(item.get("checked_at"))
                age_h = (now - t).total_seconds() / 3600 if t else None
                observed = str(item.get("status") or "unknown")
                account = str(item.get("account") or "")
                expected = str(p.get("expected_account") or "")
                if not t or age_h is None or age_h > float(p["max_age_h"]):
                    status, why = "unknown", "接続確認が期限切れまたは時刻なし"
                elif observed == "disconnected":
                    status, why = "stale", "未接続"
                elif expected and account != expected:
                    status, why = "stale", "接続アカウントが期待値と不一致"
                elif observed == "ok":
                    status, why = "ok", "接続確認済み"
                else:
                    status, why = "unknown", "接続状態を確認できない"
            except (OSError, ValueError, KeyError) as exc:
                t, age_h = None, None
                status, why = "unknown", f"接続記録の読取不能: {type(exc).__name__}"
            rows.append({**p, "last": t.isoformat() if t else None, "age_h": age_h, "stale": status != "ok", "status": status, "why": why})
            continue
        if p.get("kind") == "mirror_content":
            def resolve(name):
                path = Path(str(p[name])).expanduser()
                return path if path.is_absolute() else REPO / path
            try:
                source, mirror = resolve("source"), resolve("mirror")
                same = source.read_bytes() == mirror.read_bytes()
                status, why = ("ok", "内容一致") if same else ("stale", "正本と写しの内容が不一致")
            except OSError as exc:
                status, why = "unknown", f"読取不能: {type(exc).__name__}"
            rows.append({**p, "last": None, "age_h": None, "stale": status != "ok", "status": status, "why": why})
            continue
        try:
            t, why = getter(p)
        except (OSError, subprocess.SubprocessError, ValueError) as exc:
            # 一つの取得失敗で他の監視を止めない。例外本文には秘密が混ざりうる。
            t, why = None, f"確認不能: {type(exc).__name__}"
        age_h = (now - t).total_seconds() / 3600 if t else None
        stale = age_h is None or age_h > float(p["max_age_h"])
        status = "unknown" if age_h is None else ("stale" if stale else "ok")
        rows.append({**p, "last": t.isoformat() if t else None, "age_h": age_h, "stale": stale, "status": status, "why": why})
    return rows


def diff_state(rows: list[dict[str, Any]], prev_stale: set[str]) -> tuple[list[dict], list[dict]]:
    now_stale = {r["id"] for r in rows if r["stale"]}
    newly = [r for r in rows if r.get("notify", True) and r["id"] in now_stale - prev_stale]
    recovered = [r for r in rows if r.get("notify", True) and r["id"] in prev_stale - now_stale]
    return newly, recovered


def _age(r: dict[str, Any]) -> str:
    if r["age_h"] is None:
        return r.get("why") or "不明"
    h = r["age_h"]
    return f"{h / 24:.1f}日前" if h >= 48 else f"{h:.0f}時間前"


def build_message(newly: list[dict], recovered: list[dict]) -> str:
    lines = ["【ops】315 連携健全性・鮮度監視"]
    for r in newly:
        if r.get("status") == "unknown":
            lines.append(f"🟡 {r['label']}: 未確認（{_age(r)}）")
        elif r.get("kind") == "mirror_content":
            lines.append(f"🔴 {r['label']}: {r['why']}")
        else:
            lines.append(f"🔴 {r['label']}: 最終成功 {_age(r)}（上限 {r['max_age_h']}h）")
        lines.append(f"　担当 {r['owner']}／まず: {r['action']}")
    for r in recovered:
        lines.append(f"🟢 回復 {r['label']}: 最終成功 {_age(r)}")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--post", action="store_true")
    args = ap.parse_args()
    if os.environ.get("JARVIS_FRESHNESS_WATCH_DISABLE") == "1":
        print(f"{LOG}: disabled")
        return 0

    cfg = yaml.safe_load(CONFIG.read_text(encoding="utf-8")) or {}
    now = datetime.now(timezone.utc)
    rows = evaluate(cfg, now)
    prev: dict[str, Any] = {}
    if STATE.is_file():
        try:
            prev = json.loads(STATE.read_text(encoding="utf-8"))
        except ValueError:
            prev = {}
    newly, recovered = diff_state(rows, set(prev.get("stale") or []))

    for r in rows:
        mark = r["status"].upper()
        limit = f"上限{r['max_age_h']}h" if "max_age_h" in r else "内容比較"
        print(f"{mark:5} {r['id']:22} {_age(r):>10}  {limit}")
    if args.dry_run:
        if newly or recovered:
            print("--- 投稿予定 ---\n" + build_message(newly, recovered))
        return 0

    rc = 0
    if (newly or recovered) and args.post:
        r = subprocess.run(
            [
                sys.executable, str(REPO / "scripts" / "jarvis_slack_webhook_post.py"),
                "--channel", "ops", "--text", build_message(newly, recovered),
            ],
            cwd=REPO,
        )
        rc = r.returncode
    if rc == 0:
        STATE.parent.mkdir(parents=True, exist_ok=True)
        STATE.write_text(
            json.dumps(
                {
                    "checked_at": datetime.now(JST).isoformat(timespec="seconds"),
                    "stale": sorted(r["id"] for r in rows if r["stale"]),
                    "rows": [
                        {k: r.get(k) for k in ("id", "label", "last", "age_h", "stale", "max_age_h", "status", "why", "kind")}
                        for r in rows
                    ],
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
