#!/usr/bin/env python3
"""
Jarvis: 状況ウォッチのうち API だけで完結する項目を GHA / クラウドから判定し watch_status へ upsert。

Mac の jarvis_situation_watch（.jarvis_state 依存）はフォールバックのまま残す。
本スクリプトは「クラウドで見られる鮮度・WeStudy CI」だけを上書きする。

  cd ~/git-repos && set -a && source .env.jarvis_private && set +a
  python scripts/jarvis_gha_situation_watch.py --dry-run
  python scripts/jarvis_gha_situation_watch.py --push

環境: JARVIS_SUPABASE_URL / JARVIS_SUPABASE_SERVICE_ROLE_KEY
任意: GITHUB_TOKEN または gh 認証（WeStudy 週次）
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

JST = ZoneInfo("Asia/Tokyo")
WESTUDY_WORKFLOW = "westudy-raimo-weekly.yml"
STALE_MAC_HOURS = 36
STALE_GHA_HOURS = 30


def now_iso() -> str:
    return datetime.now(JST).strftime("%Y-%m-%dT%H:%M:%S%z")


def parse_meta_dt(s: str | None) -> datetime | None:
    if not s:
        return None
    t = str(s).strip()
    try:
        if t.endswith("Z"):
            return datetime.fromisoformat(t.replace("Z", "+00:00"))
        # +0900 / +09:00
        if len(t) >= 5 and (t[-5] in "+-" or t[-6] in "+-"):
            if t[-3] != ":" and len(t) >= 5 and t[-5] in "+-":
                t = t[:-2] + ":" + t[-2:]
            return datetime.fromisoformat(t)
        return datetime.fromisoformat(t).replace(tzinfo=JST)
    except ValueError:
        return None


def hours_ago(dt: datetime | None) -> float | None:
    if not dt:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=JST)
    return (datetime.now(timezone.utc) - dt.astimezone(timezone.utc)).total_seconds() / 3600.0


def fetch_sync_meta(sb) -> dict[str, str]:
    r = sb.table("sync_meta").select("key,value").execute()
    return {str(x["key"]): str(x.get("value") or "") for x in (r.data or [])}


def check_westudy() -> dict[str, Any]:
    """gh run list。失敗時は level=attention で理由を載せる。"""
    cmd = [
        "gh",
        "run",
        "list",
        f"--workflow={WESTUDY_WORKFLOW}",
        "--limit",
        "3",
        "--json",
        "databaseId,conclusion,status,createdAt,url,displayTitle",
    ]
    try:
        out = subprocess.check_output(cmd, text=True, stderr=subprocess.STDOUT, timeout=60)
        runs = json.loads(out or "[]")
    except FileNotFoundError:
        return {
            "id": "westudy_weekly",
            "title": "WeStudy週次CI",
            "category": "ops",
            "level": "attention",
            "summary": "gh 未インストール（GHA ランナーでは通常あり）",
            "detail": None,
            "source": "gha:gh",
            "cursor_prompt": "WeStudy週次の GitHub Actions を確認して。",
            "status": "active",
            "checked_at": now_iso(),
        }
    except (subprocess.CalledProcessError, json.JSONDecodeError, subprocess.TimeoutExpired) as e:
        return {
            "id": "westudy_weekly",
            "title": "WeStudy週次CI",
            "category": "ops",
            "level": "attention",
            "summary": f"gh 取得失敗: {e}",
            "detail": None,
            "source": "gha:gh",
            "cursor_prompt": "WeStudy週次の GitHub Actions を確認して。",
            "status": "active",
            "checked_at": now_iso(),
        }

    if not runs:
        return {
            "id": "westudy_weekly",
            "title": "WeStudy週次CI",
            "category": "ops",
            "level": "info",
            "summary": "実行履歴なし",
            "detail": None,
            "source": "gha:gh",
            "cursor_prompt": "WeStudy週次の GitHub Actions を確認して。",
            "status": "active",
            "checked_at": now_iso(),
        }

    latest = runs[0]
    conc = latest.get("conclusion") or latest.get("status") or "—"
    level = "ok"
    if conc == "failure":
        level = "warn"
    elif conc not in ("success", "completed"):
        level = "attention"
    return {
        "id": "westudy_weekly",
        "title": "WeStudy週次CI",
        "category": "ops",
        "level": level,
        "summary": f"直近 {conc}（run {latest.get('databaseId')}）",
        "detail": latest.get("url"),
        "source": "gha:gh",
        "cursor_prompt": "WeStudy週次の GitHub Actions を確認して。失敗ならログ要約と再実行案を。",
        "status": "active",
        "checked_at": now_iso(),
        "payload": {"run": latest},
    }


def check_collect_freshness(meta: dict[str, str]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    gha_at = parse_meta_dt(meta.get("gha_triage_pushed_at"))
    mac_at = parse_meta_dt(meta.get("mac_triage_pushed_at") or meta.get("triage_pushed_at"))
    hb_at = parse_meta_dt(meta.get("gha_heartbeat_at"))
    src = meta.get("triage_source") or "—"

    gha_h = hours_ago(gha_at)
    if gha_h is None:
        level, summary = "attention", "GHA トリアージ未実行（gha_triage_pushed_at なし）"
    elif gha_h > STALE_GHA_HOURS:
        level, summary = "warn", f"GHA トリアージが約 {gha_h:.0f} 時間前（閾値 {STALE_GHA_HOURS}h）"
    else:
        level, summary = "ok", f"GHA トリアージ約 {gha_h:.1f} 時間前 / source={src}"

    items.append(
        {
            "id": "gha_collect_freshness",
            "title": "収集鮮度（GHA）",
            "category": "ops",
            "level": level,
            "summary": summary,
            "detail": meta.get("gha_triage_pushed_at") or None,
            "source": "gha:sync_meta",
            "cursor_prompt": "Jarvis ダッシュボードの GHA Gmail トリアージと sync_meta を確認して。",
            "status": "active",
            "checked_at": now_iso(),
        }
    )

    mac_h = hours_ago(mac_at)
    if mac_h is None:
        m_level, m_sum = "info", "Mac トリアージ push 未記録（GHA のみでも可）"
    elif mac_h > STALE_MAC_HOURS:
        m_level, m_sum = "attention", f"Mac push が約 {mac_h:.0f} 時間前（CHRLINE/MD は Mac 依存）"
    else:
        m_level, m_sum = "ok", f"Mac push 約 {mac_h:.1f} 時間前"

    items.append(
        {
            "id": "mac_collect_freshness",
            "title": "収集鮮度（Mac）",
            "category": "ops",
            "level": m_level,
            "summary": m_sum,
            "detail": meta.get("mac_triage_pushed_at") or meta.get("triage_pushed_at"),
            "source": "gha:sync_meta",
            "cursor_prompt": "Mac 夜間トリアージ／jarvis_dashboard_push の最終時刻を確認して。",
            "status": "active",
            "checked_at": now_iso(),
        }
    )

    hb_h = hours_ago(hb_at)
    if hb_h is None:
        h_level, h_sum = "info", "GHA 心拍未記録"
    elif hb_h > 48:
        h_level, h_sum = "warn", f"心拍が約 {hb_h:.0f} 時間前（休止リスク）"
    else:
        h_level, h_sum = "ok", f"心拍約 {hb_h:.1f} 時間前"

    items.append(
        {
            "id": "gha_heartbeat",
            "title": "Supabase心拍（GHA）",
            "category": "ops",
            "level": h_level,
            "summary": h_sum,
            "detail": meta.get("gha_heartbeat_at"),
            "source": "gha:sync_meta",
            "cursor_prompt": "jarvis-dashboard-heartbeat.yml と sync_meta.gha_heartbeat_at を確認して。",
            "status": "active",
            "checked_at": now_iso(),
        }
    )
    return items


def to_row(it: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": it["id"],
        "title": it.get("title") or it["id"],
        "category": it.get("category"),
        "level": it.get("level") or "info",
        "summary": it.get("summary"),
        "detail": it.get("detail"),
        "source": it.get("source"),
        "cursor_prompt": it.get("cursor_prompt"),
        "status": it.get("status") or "active",
        "archived_at": None,
        "checked_at": it.get("checked_at") or now_iso(),
        "payload": it.get("payload") or {"origin": "gha"},
        "updated_at": now_iso(),
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--push", action="store_true")
    args = ap.parse_args(argv)
    if not args.dry_run and not args.push:
        args.dry_run = True

    url = (os.environ.get("JARVIS_SUPABASE_URL") or "").strip()
    key = (os.environ.get("JARVIS_SUPABASE_SERVICE_ROLE_KEY") or "").strip()
    if not url or not key:
        print("JARVIS_SUPABASE_URL / JARVIS_SUPABASE_SERVICE_ROLE_KEY が必要", file=sys.stderr)
        return 1

    from supabase import create_client

    sb = create_client(url, key)
    meta = fetch_sync_meta(sb)
    items = check_collect_freshness(meta) + [check_westudy()]

    print(json.dumps({"count": len(items), "items": items}, ensure_ascii=False, indent=2))
    if args.dry_run:
        return 0

    # リモートで archived のものは潰さない
    remote_arch: set[str] = set()
    try:
        r = sb.table("watch_status").select("id").eq("status", "archived").execute()
        remote_arch = {str(x["id"]) for x in (r.data or [])}
    except Exception as e:
        print(f"# archive merge skip: {e}", file=sys.stderr)

    rows = []
    for it in items:
        if it["id"] in remote_arch:
            continue
        rows.append(to_row(it))
    if rows:
        sb.table("watch_status").upsert(rows, on_conflict="id").execute()
    meta_now = now_iso()
    sb.table("sync_meta").upsert(
        [
            {"key": "gha_watch_pushed_at", "value": meta_now, "updated_at": meta_now},
            {"key": "watch_source", "value": "gha", "updated_at": meta_now},
        ],
        on_conflict="key",
    ).execute()
    print(f"# watch upserted {len(rows)}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
