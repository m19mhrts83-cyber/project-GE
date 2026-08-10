#!/usr/bin/env python3
"""
815 オプチャ・スレッド取得健全性 → sync_meta + watch_status

静かな失敗（登録0件で正常終了・追記0が続く等）を検知し、
ダッシュボード /openchat/health 用の JSON を push する。

  cd ~/git-repos && set -a && source .env.jarvis_private && set +a
  python scripts/jarvis_openchat_thread_health.py
  python scripts/jarvis_openchat_thread_health.py --dry-run
  python scripts/jarvis_openchat_thread_health.py --push
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

JST = ZoneInfo("Asia/Tokyo")
REPO = Path(__file__).resolve().parents[1]
STATE = REPO / ".jarvis_state"
HEALTH_PATH = STATE / "openchat_thread_health.json"
ROUTES_YAML = REPO / "line_unofficial_poc" / "open_chat_routes.yaml"
WATCH_STATUS = (
    REPO / "line_unofficial_poc" / ".line_auth" / ".chrline_open_chat_watch_status.json"
)
OPENCHAT_BASE = Path(
    "~/Library/CloudStorage/OneDrive-個人用/215_神・大家さん倶楽部"
    "/C2_ルーティン作業/26_パートナー社への相談/815_神大家オプチャ"
).expanduser()

BOOTSTRAP_HINT = (
    "cd ~/git-repos/line_unofficial_poc && ./launchd/open_chat_watch_pause.sh && "
    "./run_patch.sh chrline_open_chat_to_md.py --allow-qr-login "
    "--discover-only --discover-from-yoritoori --auto-append-thread-mids "
    "--route-ids {route_id} && ./launchd/open_chat_watch_resume.sh"
)


def now_iso() -> str:
    return datetime.now(tz=JST).isoformat(timespec="seconds")


def today() -> date:
    return datetime.now(tz=JST).date()


def load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return raw if isinstance(raw, dict) else {}
    except Exception:
        return {}


def load_routes() -> list[dict[str, Any]]:
    try:
        import yaml
    except Exception:
        print("エラー: PyYAML が必要です", file=sys.stderr)
        return []
    if not ROUTES_YAML.is_file():
        return []
    data = yaml.safe_load(ROUTES_YAML.read_text(encoding="utf-8")) or {}
    routes = data.get("routes") or []
    out = []
    for r in routes:
        if not isinstance(r, dict):
            continue
        out.append(
            {
                "id": str(r.get("id") or "").strip(),
                "org_label": str(r.get("org_label") or r.get("title_substring") or "").strip(),
                "include_threads": bool(r.get("include_threads", True)),
                "thread_mids": [str(x) for x in (r.get("thread_mids") or []) if x],
                "output_md": Path(str(r.get("output_md") or "")).expanduser(),
            }
        )
    return [r for r in out if r["id"]]


def count_md_headings(md: Path, *, days: int = 14) -> dict[str, int]:
    """直近 N 日の 【スレッド】/【スレッド返信】 件数。"""
    result = {"thread": 0, "reply": 0, "main": 0}
    if not md.is_file():
        return result
    try:
        text = md.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return result
    start = today() - timedelta(days=max(0, days - 1))
    # ### YYYY/MM/DD HH:MM …【スレッド】
    for m in re.finditer(
        r"^### (\d{4}/\d{2}/\d{2}).*?(【スレッド返信】|【スレッド】|【メイン】)",
        text,
        re.M,
    ):
        try:
            d = datetime.strptime(m.group(1), "%Y/%m/%d").date()
        except ValueError:
            continue
        if d < start:
            continue
        kind = m.group(2)
        if kind == "【スレッド】":
            result["thread"] += 1
        elif kind == "【スレッド返信】":
            result["reply"] += 1
        else:
            result["main"] += 1
    return result


def daily_thread_series(routes: list[dict[str, Any]], *, days: int = 30) -> list[dict[str, Any]]:
    """日付ごとの【スレッド】追記件数（route内訳付き）。"""
    start = today() - timedelta(days=days - 1)
    by_day: dict[str, dict[str, int]] = {}
    for i in range(days):
        d = start + timedelta(days=i)
        by_day[d.isoformat()] = {}

    for route in routes:
        md = route["output_md"]
        if not md.is_file():
            continue
        try:
            text = md.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        rid = route["id"]
        for m in re.finditer(r"^### (\d{4}/\d{2}/\d{2}).*?【スレッド】", text, re.M):
            try:
                d = datetime.strptime(m.group(1), "%Y/%m/%d").date()
            except ValueError:
                continue
            if d < start:
                continue
            key = d.isoformat()
            if key not in by_day:
                by_day[key] = {}
            by_day[key][rid] = by_day[key].get(rid, 0) + 1

    series = []
    for key in sorted(by_day.keys()):
        routes_counts = by_day[key]
        series.append(
            {
                "date": key,
                "total": sum(routes_counts.values()),
                "routes": routes_counts,
            }
        )
    return series


def heartbeat_age_sec(watch: dict[str, Any]) -> float | None:
    hb = watch.get("heartbeat_at") or watch.get("updated_at")
    if not hb:
        return None
    try:
        dt = datetime.fromisoformat(str(hb).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=JST)
        return (datetime.now(tz=JST) - dt.astimezone(JST)).total_seconds()
    except Exception:
        return None


def evaluate_route(
    route: dict[str, Any],
    latest_entry: dict[str, Any] | None,
    history: dict[str, Any],
    md_counts: dict[str, int],
) -> dict[str, Any]:
    rid = route["id"]
    registered = len(route["thread_mids"])
    include = bool(route["include_threads"])
    replies_14 = int(md_counts.get("reply") or 0)
    threads_14 = int(md_counts.get("thread") or 0)
    main_14 = int(md_counts.get("main") or 0)

    level = "ok"
    reasons: list[str] = []
    action = ""

    if include and registered == 0 and replies_14 > 0:
        level = "attention"
        reasons.append(
            f"thread_mids 未登録なのに直近14日【スレッド返信】{replies_14}件"
            "（専用スレ取得できていない静かな失敗）"
        )
        action = BOOTSTRAP_HINT.format(route_id=rid)

    # 登録あり・7日連続 appended_threads=0、かつ main 追記あり
    if include and registered > 0 and level == "ok":
        days_zero = 0
        main_recent = 0
        for day in sorted(history.keys())[-7:]:
            day_routes = (history.get(day) or {}).get("routes") or {}
            ent = day_routes.get(rid) or {}
            if int(ent.get("appended_threads") or 0) == 0:
                days_zero += 1
            main_recent += int(ent.get("appended_main") or 0)
        # MD 側の main も参考
        if days_zero >= 7 and (main_recent > 0 or main_14 > 0) and threads_14 == 0:
            level = "attention"
            reasons.append(
                f"登録{registered}件なのに7日連続スレ追記0（メインは動いている）"
            )
            action = action or BOOTSTRAP_HINT.format(route_id=rid)

    deleted = int((latest_entry or {}).get("deleted") or 0)
    closed = int((latest_entry or {}).get("closed") or 0)
    ok_n = int((latest_entry or {}).get("ok") or 0)
    if registered > 0 and (deleted + closed) >= max(registered * 0.8, 1) and ok_n == 0:
        if level == "ok":
            level = "info"
        reasons.append(
            f"登録の大半が deleted/closed（構造限界: deleted={deleted} closed={closed}）"
        )

    if include and registered == 0 and replies_14 == 0 and threads_14 == 0:
        if level == "ok":
            level = "info"
            reasons.append("thread_mids 0件・直近スレ活動なし（問題なしの可能性）")

    return {
        "route_id": rid,
        "org_label": route["org_label"],
        "include_threads": include,
        "thread_mids_registered": registered,
        "md_threads_14d": threads_14,
        "md_replies_14d": replies_14,
        "md_main_14d": main_14,
        "appended_threads": int((latest_entry or {}).get("appended_threads") or 0),
        "appended_main": int((latest_entry or {}).get("appended_main") or 0),
        "ok": ok_n,
        "deleted": deleted,
        "closed": closed,
        "last_ok_at": (latest_entry or {}).get("last_ok_at"),
        "run_at": (latest_entry or {}).get("run_at"),
        "level": level,
        "reasons": reasons,
        "action": action,
        "needs_bootstrap": bool(action),
    }


def build_report() -> dict[str, Any]:
    routes = load_routes()
    health = load_json(HEALTH_PATH)
    watch = load_json(WATCH_STATUS)
    history = health.get("history") if isinstance(health.get("history"), dict) else {}
    latest = health.get("latest") if isinstance(health.get("latest"), dict) else {}
    latest_routes = latest.get("routes") if isinstance(latest.get("routes"), dict) else {}

    route_evals: list[dict[str, Any]] = []
    for route in routes:
        md_counts = count_md_headings(route["output_md"], days=14)
        route_evals.append(
            evaluate_route(
                route,
                latest_routes.get(route["id"]),
                history,
                md_counts,
            )
        )

    level_rank = {"attention": 0, "warn": 1, "info": 2, "ok": 3}
    worst = "ok"
    for ev in route_evals:
        if level_rank.get(ev["level"], 9) < level_rank.get(worst, 9):
            worst = ev["level"]

    hb_age = heartbeat_age_sec(watch)
    watch_level = "ok"
    watch_notes: list[str] = []
    state = str(watch.get("state") or "")
    if not watch:
        watch_level = "attention"
        watch_notes.append("常時監視 status なし")
    elif state and state != "running":
        watch_level = "attention"
        watch_notes.append(f"launchd state={state}")
    if hb_age is not None and hb_age > 180:
        watch_level = "attention"
        watch_notes.append(f"heartbeat 停止（{int(hb_age)}秒前）")
    err = str(watch.get("last_write_error") or "").strip()
    if err:
        watch_level = "attention"
        watch_notes.append(f"書込エラー: {err[:120]}")

    if level_rank.get(watch_level, 9) < level_rank.get(worst, 9):
        worst = watch_level

    attention_routes = [r for r in route_evals if r["level"] == "attention"]
    series = daily_thread_series(routes, days=30)
    threads_today = next(
        (s["total"] for s in series if s["date"] == today().isoformat()),
        0,
    )

    summary_parts = [
        f"要確認ルート {len(attention_routes)}/{len(route_evals)}",
        f"今日【スレッド】{threads_today}件",
    ]
    if watch.get("state"):
        summary_parts.insert(0, f"launchd {watch.get('state')}")
    if hb_age is not None:
        if hb_age < 120:
            summary_parts.append("heartbeat 直近")
        else:
            summary_parts.append(f"heartbeat {int(hb_age)}秒前")
    if watch_notes:
        summary_parts.extend(watch_notes[:2])
    if attention_routes:
        summary_parts.append(
            "問題: " + ", ".join(r["org_label"] or r["route_id"] for r in attention_routes[:3])
        )

    return {
        "generated_at": now_iso(),
        "worst_level": worst,
        "summary": " · ".join(summary_parts),
        "watch": {
            "state": watch.get("state"),
            "heartbeat_at": watch.get("heartbeat_at"),
            "heartbeat_age_sec": int(hb_age) if hb_age is not None else None,
            "last_append_at": watch.get("last_append_at"),
            "last_append_route": watch.get("last_append_route"),
            "last_write_error": err or None,
            "level": watch_level,
            "notes": watch_notes,
        },
        "batch": {
            "latest_day": health.get("latest_day"),
            "run_at": latest.get("run_at") or health.get("updated_at"),
        },
        "threads_today": threads_today,
        "attention_count": len(attention_routes),
        "routes": route_evals,
        "daily_series": series,
        "source": "jarvis_openchat_thread_health",
    }


def sb_client():
    url = (os.environ.get("JARVIS_SUPABASE_URL") or "").strip()
    key = (os.environ.get("JARVIS_SUPABASE_SERVICE_ROLE_KEY") or "").strip()
    if not url or not key:
        raise RuntimeError("JARVIS_SUPABASE_URL / JARVIS_SUPABASE_SERVICE_ROLE_KEY が必要")
    from supabase import create_client

    return create_client(url, key)


def push_report(report: dict[str, Any]) -> None:
    sb = sb_client()
    now = now_iso()
    sb.table("sync_meta").upsert(
        {
            "key": "openchat_thread_health",
            "value": json.dumps(report, ensure_ascii=False),
            "updated_at": now,
        },
        on_conflict="key",
    ).execute()

    level = report.get("worst_level") or "info"
    payload = {
        "origin": "openchat_thread_health",
        "show_banner": level in ("attention", "warn"),
        "worst_level": level,
        "heartbeat_at": (report.get("watch") or {}).get("heartbeat_at"),
        "threads_today": report.get("threads_today"),
        "attention_count": report.get("attention_count"),
        "routes": report.get("routes") or [],
        "batch_run_at": (report.get("batch") or {}).get("run_at"),
        "href": "/openchat/health",
    }
    sb.table("watch_status").upsert(
        {
            "id": "openchat_threads",
            "title": "オプチャ・スレッド取得",
            "category": "ops",
            "level": level,
            "summary": report.get("summary") or "",
            "detail": "/openchat/health",
            "source": "openchat_thread_health",
            "cursor_prompt": (
                "ダッシュボード /openchat/health を確認。"
                " 登録0件＋【スレッド返信】ありなら "
                "chrline_thread_bootstrap.py --discover-from-yoritoori を案内。"
            ),
            "status": "active",
            "archived_at": None,
            "payload": payload,
            "checked_at": now,
            "updated_at": now,
        },
        on_conflict="id",
    ).execute()
    print("# pushed sync_meta.openchat_thread_health + watch_status.openchat_threads")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--push", action="store_true")
    args = ap.parse_args(argv)
    if not args.dry_run and not args.push:
        args.dry_run = True

    report = build_report()
    # ローカルにも保存（バッチ未実行でも MD 判定結果を残す）
    STATE.mkdir(parents=True, exist_ok=True)
    snapshot = {
        "updated_at": report["generated_at"],
        "latest_day": today().isoformat(),
        "latest": {
            "run_at": report["generated_at"],
            "routes": {
                r["route_id"]: {
                    "route_id": r["route_id"],
                    "org_label": r["org_label"],
                    "include_threads": r["include_threads"],
                    "thread_mids_registered": r["thread_mids_registered"],
                    "appended_threads": r["appended_threads"],
                    "appended_main": r["appended_main"],
                    "ok": r["ok"],
                    "deleted": r["deleted"],
                    "closed": r["closed"],
                    "last_ok_at": r.get("last_ok_at"),
                    "run_at": r.get("run_at") or report["generated_at"],
                    "level": r["level"],
                }
                for r in (report.get("routes") or [])
            },
        },
        "history": load_json(HEALTH_PATH).get("history") or {},
        "last_report": {
            "worst_level": report.get("worst_level"),
            "summary": report.get("summary"),
            "attention_count": report.get("attention_count"),
        },
    }
    # history に今日の判定サマリを軽く載せる（バッチ統計が無ければ MD ベース）
    hist = snapshot["history"] if isinstance(snapshot["history"], dict) else {}
    day = today().isoformat()
    day_bucket = hist.get(day) if isinstance(hist.get(day), dict) else {}
    if not day_bucket.get("routes"):
        day_bucket["routes"] = snapshot["latest"]["routes"]
        day_bucket["run_at"] = report["generated_at"]
        hist[day] = day_bucket
        keep = sorted(hist.keys())[-30:]
        snapshot["history"] = {k: hist[k] for k in keep}
    HEALTH_PATH.write_text(
        json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        f"# wrote {HEALTH_PATH} worst={report.get('worst_level')} "
        f"attention={report.get('attention_count')}",
        file=sys.stderr,
    )

    print(
        json.dumps(
            {
                "worst_level": report.get("worst_level"),
                "attention_count": report.get("attention_count"),
                "routes": len(report.get("routes") or []),
                "summary": report.get("summary"),
            },
            ensure_ascii=False,
            indent=2,
        )
    )

    if args.dry_run:
        return 0
    try:
        push_report(report)
    except Exception as e:
        print(f"# push failed: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
