#!/usr/bin/env python3
"""KURASHIFT 株式ウォッチ — 提案・閾値評価・Todoist(Theme株式)通知。

  cd ~/git-repos && set -a && source .env.jarvis_private && set +a
  ~/selenium_env/venv/bin/python scripts/jarvis_kurashift_stock_watch.py --dry-run --eval
  ~/selenium_env/venv/bin/python scripts/jarvis_kurashift_stock_watch.py --fetch --eval --notify
  ~/selenium_env/venv/bin/python scripts/jarvis_kurashift_stock_watch.py --propose-weekly --notify
  ~/selenium_env/venv/bin/python scripts/jarvis_kurashift_stock_watch.py --activate-theme THEME_ID

自動発注はしない。判断ログは Todoist lane theme_stock。
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import yaml

from jarvis_trade_common import JST, load_watchlist, sb_client, sma

REPO = Path(__file__).resolve().parents[1]
CONFIG_PATH = REPO / "config" / "kurashift_stock_watch.yaml"
STATE_PATH = REPO / ".jarvis_state" / "kurashift_stock_watch.json"
EXAMPLE_STATE = REPO / ".jarvis_state" / "kurashift_stock_watch.example.json"
PY = Path(os.environ.get("JARVIS_PYTHON") or sys.executable)
TODOIST_CLI = REPO / "scripts" / "jarvis_todoist_api.py"
FETCH_CLI = REPO / "scripts" / "jarvis_trade_fetch_prices.py"


def now_jst() -> datetime:
    return datetime.now(JST)


def now_iso() -> str:
    return now_jst().isoformat(timespec="seconds")


def load_config() -> dict[str, Any]:
    return yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8")) or {}


def load_state() -> dict[str, Any]:
    if STATE_PATH.is_file():
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    if EXAMPLE_STATE.is_file():
        return json.loads(EXAMPLE_STATE.read_text(encoding="utf-8"))
    return {
        "version": 1,
        "disabled": False,
        "watches": {},
        "todoist_tasks_by_theme": {},
        "fired": {},
        "last_eval_at": None,
        "last_propose_at": None,
        "last_summary": None,
    }


def save_state(state: dict[str, Any]) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(
        json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def merge_seed_watches(cfg: dict[str, Any], state: dict[str, Any]) -> None:
    watches = state.setdefault("watches", {})
    for w in cfg.get("seed_watches") or []:
        sym = str(w.get("symbol") or "").strip()
        if not sym or sym in watches:
            continue
        watches[sym] = {
            "symbol": sym,
            "name": w.get("name") or sym,
            "theme_title": w.get("theme_title") or f"Watch {sym}",
            "theme_id": w.get("theme_id"),
            "active": bool(w.get("active", True)),
            "bottom_hint": w.get("bottom_hint"),
            "upside_target_pct": w.get("upside_target_pct"),
            "sell_drawdown_pct": w.get("sell_drawdown_pct"),
            "peak_since_watch": None,
            "activated_at": now_iso(),
        }


def run_fetch(*, range_: str = "6mo") -> int:
    cmd = [str(PY), str(FETCH_CLI), "--range", range_]
    print(f"# fetch: {' '.join(cmd)}", flush=True)
    return subprocess.call(cmd, cwd=str(REPO))


def load_closes(sb: Any, symbol: str, limit: int = 90) -> list[dict[str, Any]]:
    res = (
        sb.table("trade_prices")
        .select("trade_date,open,high,low,close,volume")
        .eq("symbol", symbol)
        .order("trade_date", desc=True)
        .limit(limit)
        .execute()
    )
    rows = list(res.data or [])
    rows.reverse()
    return rows


def compute_levels(
    closes: list[dict[str, Any]], thr: dict[str, Any]
) -> dict[str, Any] | None:
    if len(closes) < 10:
        return None
    lookback = int(thr.get("lookback_days") or 60)
    window = closes[-lookback:] if len(closes) >= lookback else closes
    lows = [float(r["low"] if r.get("low") is not None else r["close"]) for r in window]
    highs = [float(r["high"] if r.get("high") is not None else r["close"]) for r in window]
    close_vals = [float(r["close"]) for r in window]
    period_low = min(lows)
    period_high = max(highs)
    last = close_vals[-1]
    bottom_buf = float(thr.get("bottom_buffer_pct") or 2.0) / 100.0
    bottom_hint = period_low * (1.0 + bottom_buf)
    sma20 = sma(close_vals, min(20, len(close_vals)))
    rebound_from_low = (
        (last - period_low) / period_low * 100.0 if period_low > 0 else 0.0
    )
    return {
        "close": last,
        "trade_date": window[-1]["trade_date"],
        "period_low": period_low,
        "period_high": period_high,
        "bottom_hint": bottom_hint,
        "sma20": sma20,
        "rebound_from_low_pct": rebound_from_low,
    }


def eval_symbol(
    watch: dict[str, Any], levels: dict[str, Any], thr: dict[str, Any]
) -> list[dict[str, Any]]:
    signals: list[dict[str, Any]] = []
    close = float(levels["close"])
    bottom = float(watch.get("bottom_hint") or levels["bottom_hint"])
    near_pct = float(thr.get("near_bottom_pct") or 1.5) / 100.0
    upside_ready = float(thr.get("upside_ready_pct") or 5.0)
    upside_target = float(
        watch.get("upside_target_pct") or thr.get("upside_target_pct") or 12.0
    )
    sell_dd = float(
        watch.get("sell_drawdown_pct") or thr.get("sell_drawdown_pct") or 8.0
    )

    if close <= bottom * (1.0 + near_pct):
        signals.append(
            {
                "kind": "near_bottom",
                "message": (
                    f"底値近く close={close:.1f} 底値目安={bottom:.1f}"
                    f"（期間安={levels['period_low']:.1f}）"
                ),
            }
        )

    rebound = float(levels.get("rebound_from_low_pct") or 0.0)
    if rebound >= upside_ready and close > bottom:
        signals.append(
            {
                "kind": "upside_ready",
                "message": (
                    f"安値から反発 {rebound:.1f}%（目安≥{upside_ready}%）"
                    f" close={close:.1f} 上昇目標={upside_target}%"
                ),
            }
        )

    peak = watch.get("peak_since_watch")
    peak_f = float(peak) if peak is not None else float(levels["period_high"])
    peak_f = max(peak_f, close)
    watch["peak_since_watch"] = peak_f
    if peak_f > 0:
        dd = (peak_f - close) / peak_f * 100.0
        if rebound >= upside_target and dd >= sell_dd * 0.5:
            signals.append(
                {
                    "kind": "sell_signal",
                    "message": (
                        f"目標近傍後の押し close={close:.1f} 監視高値={peak_f:.1f}"
                        f" 下落={dd:.1f}%（売閾値={sell_dd}%）"
                    ),
                }
            )
        elif dd >= sell_dd:
            signals.append(
                {
                    "kind": "sell_signal",
                    "message": (
                        f"高値からの下落 {dd:.1f}%≥{sell_dd}% "
                        f"close={close:.1f} peak={peak_f:.1f}"
                    ),
                }
            )
    return signals


def score_instrument(it: dict[str, Any], levels: dict[str, Any] | None) -> float:
    if not levels:
        return 0.0
    score = 0.4
    rebound = float(levels.get("rebound_from_low_pct") or 0.0)
    # 沈み寄り（底付近）を高スコア
    if rebound <= 3.0:
        score += 0.35
    elif rebound <= 8.0:
        score += 0.2
    close = float(levels["close"])
    bottom = float(levels["bottom_hint"])
    if close <= bottom * 1.03:
        score += 0.2
    theme = str(it.get("theme") or "")
    if theme in {"ai", "space", "mega_us", "japan_core"}:
        score += 0.05
    return min(score, 1.0)


def kurashift_urls(cfg: dict[str, Any], theme_id: str | None = None) -> list[str]:
    base = str((cfg.get("kurashift") or {}).get("base_url") or "").rstrip("/")
    path = str((cfg.get("kurashift") or {}).get("stock_watch_path") or "/stock-watch")
    links = [f"{base}{path}"]
    if theme_id:
        links.append(f"{base}/themes/{theme_id}")
    return links


def comment_body(
    *,
    summary: str,
    confirm: str,
    cfg: dict[str, Any],
    theme_id: str | None = None,
) -> str:
    lines = [
        f"サマリ: {summary}",
        f"確認: {confirm}",
        "アウトプット:",
    ]
    for u in kurashift_urls(cfg, theme_id):
        label = "Theme" if "/themes/" in u else "stock-watch"
        lines.append(f"- [{label}]({u})")
    return "\n".join(lines)


def todoist_env() -> dict[str, str]:
    """Theme株式は admin 所有。OWNER があれば CLI はそちらを使う。"""
    env = os.environ.copy()
    owner = (os.environ.get("TODOIST_API_TOKEN_OWNER") or "").strip()
    if owner:
        env["TODOIST_API_TOKEN"] = owner
    return env


def todoist_create(
    *,
    lane: str,
    title: str,
    status: str,
    note: str,
    comment: str,
    dry_run: bool,
) -> dict[str, Any]:
    if dry_run:
        print(f"# dry-run todoist create lane={lane} status={status} title={title}")
        return {"id": None, "dry_run": True}
    cmd = [
        str(PY),
        str(TODOIST_CLI),
        "create-task",
        "--lane",
        lane,
        "--title",
        title,
        "--status",
        status,
        "--note",
        note,
        "--comment",
        comment,
        "--json",
    ]
    proc = subprocess.run(
        cmd, cwd=str(REPO), capture_output=True, text=True, env=todoist_env()
    )
    if proc.returncode != 0:
        print(proc.stderr or proc.stdout, file=sys.stderr)
        raise RuntimeError(f"todoist create-task failed rc={proc.returncode}")
    out = (proc.stdout or "").strip().splitlines()
    raw = out[-1] if out else "{}"
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"raw": proc.stdout}


def todoist_comment(*, task_id: str, comment: str, dry_run: bool) -> None:
    if dry_run:
        print(f"# dry-run todoist comment task={task_id}")
        return
    cmd = [
        str(PY),
        str(TODOIST_CLI),
        "comment",
        "--task-id",
        task_id,
        "--comment",
        comment,
    ]
    proc = subprocess.run(
        cmd, cwd=str(REPO), capture_output=True, text=True, env=todoist_env()
    )
    if proc.returncode != 0:
        print(proc.stderr or proc.stdout, file=sys.stderr)
        raise RuntimeError(f"todoist comment failed rc={proc.returncode}")


def todoist_owner_confirm(*, task_id: str, lane: str, dry_run: bool) -> None:
    if dry_run:
        print(f"# dry-run todoist owner_confirm task={task_id}")
        return
    cmd = [
        str(PY),
        str(TODOIST_CLI),
        "update-status",
        "--task-id",
        task_id,
        "--lane",
        lane,
        "--status",
        "オーナー確認",
    ]
    proc = subprocess.run(
        cmd, cwd=str(REPO), capture_output=True, text=True, env=todoist_env()
    )
    if proc.returncode != 0:
        print(proc.stderr or proc.stdout, file=sys.stderr)
        raise RuntimeError(f"todoist update-status failed rc={proc.returncode}")


def fired_key(kind: str, symbol: str, day: str) -> str:
    return f"{kind}:{symbol}:{day}"


def is_deduped(state: dict[str, Any], key: str, hours: float) -> bool:
    fired = state.get("fired") or {}
    rec = fired.get(key)
    if not rec:
        return False
    try:
        at = datetime.fromisoformat(str(rec.get("at")))
    except ValueError:
        return False
    if at.tzinfo is None:
        at = at.replace(tzinfo=JST)
    return now_jst() - at < timedelta(hours=hours)


def mark_fired(state: dict[str, Any], key: str, meta: dict[str, Any]) -> None:
    state.setdefault("fired", {})[key] = {"at": now_iso(), **meta}


def upsert_sync_meta(
    sb: Any, summary: dict[str, Any], *, watches: dict[str, Any] | None = None
) -> None:
    ts = now_iso()
    rows = [
        {"key": "stock_watch_at", "value": ts, "updated_at": ts},
        {
            "key": "stock_watch_summary",
            "value": json.dumps(summary, ensure_ascii=False)[:8000],
            "updated_at": ts,
        },
    ]
    if watches is not None:
        slim = {
            k: {
                "symbol": v.get("symbol"),
                "name": v.get("name"),
                "theme_title": v.get("theme_title"),
                "theme_id": v.get("theme_id"),
                "active": v.get("active"),
                "bottom_hint": v.get("bottom_hint"),
                "upside_target_pct": v.get("upside_target_pct"),
                "sell_drawdown_pct": v.get("sell_drawdown_pct"),
            }
            for k, v in watches.items()
        }
        rows.append(
            {
                "key": "stock_watch_watches",
                "value": json.dumps(slim, ensure_ascii=False)[:12000],
                "updated_at": ts,
            }
        )
    sb.table("sync_meta").upsert(rows, on_conflict="key").execute()


def insert_theme_draft(
    sb: Any,
    *,
    title: str,
    hypothesis: str,
    payload: dict[str, Any],
    dry_run: bool,
) -> dict[str, Any]:
    row = {
        "title": title,
        "hypothesis": hypothesis,
        "amount_jpy": None,
        "duration_note": "衛星スリーブ・閾値監視",
        "funding_path": "立花等（未承認では実行しない）",
        "status": "draft",
        "payload": {**payload, "proposed_at": now_iso(), "kind": "stock_watch"},
        "updated_at": now_iso(),
    }
    if dry_run:
        return {"dry_run": True, **row}
    res = sb.table("kurashift_themes").insert(row).execute()
    return (res.data or [row])[0]


def cmd_eval_notify(
    cfg: dict[str, Any],
    state: dict[str, Any],
    *,
    notify: bool,
    dry_run: bool,
) -> dict[str, Any]:
    thr = cfg.get("thresholds") or {}
    notify_cfg = cfg.get("notify") or {}
    lane = str(notify_cfg.get("todoist_lane") or "theme_stock")
    dedupe_h = float(notify_cfg.get("dedupe_hours") or 48)
    owner_kinds = set(notify_cfg.get("owner_confirm_kinds") or [])
    sb = sb_client()
    signals_out: list[dict[str, Any]] = []
    evaluated = 0

    for sym, watch in list((state.get("watches") or {}).items()):
        if not watch.get("active", True):
            continue
        closes = load_closes(sb, sym)
        levels = compute_levels(closes, thr)
        if not levels:
            continue
        evaluated += 1
        if watch.get("bottom_hint") is None:
            watch["bottom_hint"] = levels["bottom_hint"]
        sigs = eval_symbol(watch, levels, thr)
        for sig in sigs:
            day = str(levels["trade_date"])
            key = fired_key(sig["kind"], sym, day)
            if is_deduped(state, key, dedupe_h):
                continue
            item = {
                "symbol": sym,
                "name": watch.get("name") or sym,
                "kind": sig["kind"],
                "message": sig["message"],
                "theme_title": watch.get("theme_title"),
                "theme_id": watch.get("theme_id"),
                "close": levels["close"],
                "trade_date": day,
            }
            signals_out.append(item)
            if notify and notify_cfg.get("on_threshold", True):
                theme_key = str(watch.get("theme_title") or sym)
                task_id = (state.get("todoist_tasks_by_theme") or {}).get(theme_key)
                body = comment_body(
                    summary=f"{sig['kind']} {sym} {watch.get('name') or ''} {sig['message']}",
                    confirm="買う／見送り／閾値修正？",
                    cfg=cfg,
                    theme_id=watch.get("theme_id"),
                )
                if task_id:
                    todoist_comment(task_id=str(task_id), comment=body, dry_run=dry_run)
                    if sig["kind"] in owner_kinds:
                        todoist_owner_confirm(
                            task_id=str(task_id), lane=lane, dry_run=dry_run
                        )
                else:
                    created = todoist_create(
                        lane=lane,
                        title=f"[株式] {theme_key}",
                        status="オーナー確認" if sig["kind"] in owner_kinds else "進行中",
                        note="KURASHIFT 株式ウォッチ閾値アラート",
                        comment=body,
                        dry_run=dry_run,
                    )
                    tid = created.get("id") or created.get("task_id")
                    if tid:
                        state.setdefault("todoist_tasks_by_theme", {})[theme_key] = str(
                            tid
                        )
                mark_fired(
                    state,
                    key,
                    {"kind": sig["kind"], "symbol": sym, "task_theme": theme_key},
                )

    summary = {
        "evaluated": evaluated,
        "signals": len(signals_out),
        "kinds": [s["kind"] for s in signals_out],
        "at": now_iso(),
    }
    state["last_eval_at"] = now_iso()
    state["last_summary"] = summary
    if not dry_run:
        try:
            upsert_sync_meta(
                sb, summary, watches=state.get("watches") or {}
            )
        except Exception as e:
            print(f"# sync_meta soft-fail: {e}", file=sys.stderr)
    return {"summary": summary, "signals": signals_out}


def cmd_propose(
    cfg: dict[str, Any],
    state: dict[str, Any],
    *,
    notify: bool,
    dry_run: bool,
) -> dict[str, Any]:
    propose_cfg = cfg.get("propose") or {}
    thr = cfg.get("thresholds") or {}
    notify_cfg = cfg.get("notify") or {}
    lane = str(notify_cfg.get("todoist_lane") or "theme_stock")
    min_score = float(propose_cfg.get("min_score") or 0.55)
    max_themes = int(propose_cfg.get("max_themes") or 3)
    exclude_themes = set(propose_cfg.get("exclude_themes") or [])
    exclude_ac = set(propose_cfg.get("exclude_asset_classes") or [])

    sb = sb_client()
    candidates: list[dict[str, Any]] = []
    for it in load_watchlist():
        if not it.get("enabled", True):
            continue
        if (it.get("theme") or "") in exclude_themes:
            continue
        if (it.get("asset_class") or "") in exclude_ac:
            continue
        sym = it["symbol"]
        closes = load_closes(sb, sym)
        levels = compute_levels(closes, thr)
        sc = score_instrument(it, levels)
        if sc < min_score or not levels:
            continue
        candidates.append({"instrument": it, "levels": levels, "score": sc})

    candidates.sort(key=lambda x: x["score"], reverse=True)
    created: list[dict[str, Any]] = []
    for c in candidates[:max_themes]:
        it = c["instrument"]
        lv = c["levels"]
        title = f"衛星_{it.get('theme') or 'stock'}_{it.get('ticker_jp') or it['symbol']}"
        # 既存監視・既存 Todoist テーマと重複回避
        if any(
            (w.get("symbol") == it["symbol"] and w.get("active"))
            for w in (state.get("watches") or {}).values()
        ):
            continue
        if title in (state.get("todoist_tasks_by_theme") or {}):
            continue
        hyp = (
            f"{it.get('name')}（{it['symbol']}）close={lv['close']:.1f} "
            f"底値目安={lv['bottom_hint']:.1f} 安値反発={lv['rebound_from_low_pct']:.1f}% "
            f"上昇目標目安={thr.get('upside_target_pct')}% 売下落={thr.get('sell_drawdown_pct')}%。"
            "衛星スリーブのみ。NISAコアは対象外。未承認では発注しない。"
        )
        theme = insert_theme_draft(
            sb,
            title=title,
            hypothesis=hyp,
            payload={
                "symbol": it["symbol"],
                "name": it.get("name"),
                "bottom_hint": lv["bottom_hint"],
                "upside_target_pct": thr.get("upside_target_pct"),
                "sell_drawdown_pct": thr.get("sell_drawdown_pct"),
                "score": c["score"],
                "trade_date": lv["trade_date"],
            },
            dry_run=dry_run,
        )
        theme_id = theme.get("id")
        state.setdefault("watches", {})[it["symbol"]] = {
            "symbol": it["symbol"],
            "name": it.get("name"),
            "theme_title": title,
            "theme_id": theme_id,
            "active": False,  # Theme 承認後 --activate-theme で ON
            "bottom_hint": lv["bottom_hint"],
            "upside_target_pct": thr.get("upside_target_pct"),
            "sell_drawdown_pct": thr.get("sell_drawdown_pct"),
            "peak_since_watch": lv["close"],
            "proposed_at": now_iso(),
            "score": c["score"],
        }
        if notify and notify_cfg.get("on_propose", True):
            body = comment_body(
                summary=(
                    f"提案 score={c['score']:.2f} {it.get('name')} "
                    f"底値目安={lv['bottom_hint']:.1f} close={lv['close']:.1f}"
                ),
                confirm="採用して監視ON／見送り／閾値修正？",
                cfg=cfg,
                theme_id=str(theme_id) if theme_id else None,
            )
            created_t = todoist_create(
                lane=lane,
                title=f"[提案] {title}",
                status="オーナー確認",
                note="KURASHIFT 株式ウォッチ Theme 提案。承認後に監視ON。",
                comment=body,
                dry_run=dry_run,
            )
            tid = created_t.get("id") or created_t.get("task_id")
            if tid:
                state.setdefault("todoist_tasks_by_theme", {})[title] = str(tid)
        created.append(
            {
                "title": title,
                "symbol": it["symbol"],
                "score": c["score"],
                "theme_id": theme_id,
            }
        )

    state["last_propose_at"] = now_iso()
    return {"created": created, "candidates_scanned": len(candidates)}


def cmd_activate_theme(
    cfg: dict[str, Any], state: dict[str, Any], theme_id: str, *, dry_run: bool
) -> dict[str, Any]:
    sb = sb_client()
    row = (
        sb.table("kurashift_themes")
        .select("id,title,status,payload")
        .eq("id", theme_id)
        .limit(1)
        .execute()
    )
    themes = row.data or []
    if not themes:
        raise SystemExit(f"theme not found: {theme_id}")
    th = themes[0]
    payload = th.get("payload") or {}
    sym = str(payload.get("symbol") or "").strip()
    if not sym:
        # state から theme_id 逆引き
        for s, w in (state.get("watches") or {}).items():
            if str(w.get("theme_id")) == theme_id:
                sym = s
                break
    if not sym:
        raise SystemExit("payload.symbol がなく watches にも theme_id がありません")
    watch = (state.get("watches") or {}).get(sym) or {
        "symbol": sym,
        "name": payload.get("name") or sym,
        "theme_title": th.get("title"),
        "theme_id": theme_id,
        "bottom_hint": payload.get("bottom_hint"),
        "upside_target_pct": payload.get("upside_target_pct"),
        "sell_drawdown_pct": payload.get("sell_drawdown_pct"),
    }
    watch["active"] = True
    watch["theme_id"] = theme_id
    watch["theme_title"] = th.get("title") or watch.get("theme_title")
    watch["activated_at"] = now_iso()
    state.setdefault("watches", {})[sym] = watch
    if not dry_run and th.get("status") in {"draft", "consulting"}:
        sb.table("kurashift_themes").update(
            {"status": "approved", "updated_at": now_iso()}
        ).eq("id", theme_id).execute()
    print(f"# activated watch symbol={sym} theme={watch.get('theme_title')}")
    return {"symbol": sym, "theme_id": theme_id, "active": True}


def main() -> int:
    ap = argparse.ArgumentParser(description="KURASHIFT 株式ウォッチ")
    ap.add_argument("--fetch", action="store_true")
    ap.add_argument("--eval", action="store_true")
    ap.add_argument("--notify", action="store_true")
    ap.add_argument("--propose-weekly", action="store_true")
    ap.add_argument("--activate-theme", default="", help="Theme UUID を監視ON")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--range", default="6mo")
    args = ap.parse_args()

    cfg = load_config()
    if not cfg.get("enabled", True):
        print("📎 stock_watch: disabled in config")
        return 0
    state = load_state()
    if state.get("disabled"):
        print("📎 stock_watch: disabled in state")
        return 0

    merge_seed_watches(cfg, state)
    results: dict[str, Any] = {}

    if args.fetch:
        rc = run_fetch(range_=args.range)
        results["fetch_rc"] = rc
        if rc != 0 and not args.dry_run:
            print("# fetch failed; continue eval if prices exist", file=sys.stderr)

    if args.propose_weekly:
        results["propose"] = cmd_propose(
            cfg, state, notify=args.notify, dry_run=args.dry_run
        )

    if args.activate_theme:
        results["activate"] = cmd_activate_theme(
            cfg, state, args.activate_theme.strip(), dry_run=args.dry_run
        )

    if args.eval or (not args.propose_weekly and not args.activate_theme and not args.fetch):
        # default: eval when nothing else? Prefer explicit --eval
        if args.eval:
            results["eval"] = cmd_eval_notify(
                cfg, state, notify=args.notify, dry_run=args.dry_run
            )

    if not args.dry_run:
        save_state(state)
    else:
        print("# dry-run: state not saved")

    print("📎 KURASHIFT 株式ウォッチ")
    print(json.dumps(results, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
