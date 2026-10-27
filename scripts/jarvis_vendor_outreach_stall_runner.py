#!/usr/bin/env python3
"""業者開拓 stall — S2/S4/S9 のキュー枯渇・未着を検知し、自律 refill / sync / Slack。

対外 Web 送信はしない（Grok／人が送る）。Mac 側の補給・投影・報告だけ。

  cd ~/git-repos && set -a && source .env.jarvis_private && set +a
  ~/selenium_env/venv/bin/python scripts/jarvis_vendor_outreach_stall_runner.py --dry-run
  ~/selenium_env/venv/bin/python scripts/jarvis_vendor_outreach_stall_runner.py --apply --lane all
  ~/selenium_env/venv/bin/python scripts/jarvis_vendor_outreach_stall_runner.py --apply --lane s9 --force-refill
  ~/selenium_env/venv/bin/python scripts/jarvis_vendor_outreach_stall_runner.py --apply --evening
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable
from zoneinfo import ZoneInfo

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))

from jarvis_bucho_bridge_lib import (  # noqa: E402
    folder,
    list_queue_files,
    outbox_dir_for_target,
    sanitize_title,
)
from jarvis_kurashift_vendor_list import (  # noqa: E402
    LIST_PATH as S2_LIST,
    build_batch_week_payload,
    grok_weekly_kickoff,
    load_list as load_s2,
    next_pending as s2_next_pending,
    outreach_phase_settings,
    summary as s2_summary,
)
from jarvis_kurashift_mgmt_vendor_list import (  # noqa: E402
    LIST_PATH as S9_LIST,
    load_list as load_s9,
    next_pending as s9_next_pending,
    summary as s9_summary,
)
from jarvis_kurashift_repair_vendor_list import (  # noqa: E402
    LIST_PATH as S4_LIST,
    load_list as load_s4,
    next_for_contact as s4_next_for_contact,
    summary as s4_summary,
)

JST = ZoneInfo("Asia/Tokyo")
STATE_PATH = REPO / ".jarvis_state" / "vendor_outreach_stall.json"
EXAMPLE_PATH = REPO / ".jarvis_state" / "vendor_outreach_stall.example.json"
PY = Path.home() / "selenium_env" / "venv" / "bin" / "python"
SLACK_POST = REPO / "scripts" / "jarvis_slack_webhook_post.py"

LANE_CFG: dict[str, dict[str, Any]] = {
    "s2": {
        "label": "S2地場紹介",
        # Slack UI: 状態行に担当を必ず添える（2026-10-22 FB）
        "role": "地場の管理会社・仲介への紹介依頼",
        "sync": REPO / "scripts" / "jarvis_kurashift_vendor_sync.py",
        "meta_key": "vendor_outreach_stall",
        "url": "https://jarvis-trade-desk.vercel.app/realestate/vendors",
        "list_path": S2_LIST,
    },
    "s4": {
        "label": "S4修繕",
        "role": "修繕業者の開拓・見積依頼",
        "sync": REPO / "scripts" / "jarvis_kurashift_repair_vendor_sync.py",
        "meta_key": "vendor_outreach_stall_s4",
        "url": "https://jarvis-trade-desk.vercel.app/realestate/repair-vendors",
        "list_path": S4_LIST,
    },
    "s9": {
        "label": "S9管理会社",
        "role": "管理会社の事前確認・開拓",
        "sync": REPO / "scripts" / "jarvis_kurashift_mgmt_vendor_sync.py",
        "meta_key": "vendor_outreach_stall_s9",
        "url": "https://jarvis-trade-desk.vercel.app/realestate/mgmt-vendors",
        "list_path": S9_LIST,
    },
}


def lane_role(lane: str) -> str:
    return str((LANE_CFG.get(str(lane or "").lower()) or {}).get("role") or "")


def format_lane_heading(r: dict[str, Any]) -> str:
    """週次／ops 見出し。例: *S2地場紹介*（地場の…）"""
    label = str(r.get("label") or r.get("lane") or "?").strip()
    role = str(r.get("role") or lane_role(str(r.get("lane") or ""))).strip()
    if role:
        return f"*{label}*（{role}）"
    return f"*{label}*"


def build_ops_status_block(results: list[dict[str, Any]]) -> str:
    """複数レーンの現状。担当役割を必ず書く（Slack UI FB 2026-10-22）。"""
    lines = ["*現状*"]
    for r in results:
        label = str(r.get("label") or r.get("lane") or "?").strip()
        role = str(r.get("role") or lane_role(str(r.get("lane") or ""))).strip()
        status = _stall_status_ja(str(r.get("stall_status") or ""))
        detail = str(r.get("ops_reason") or "").strip()
        role_bit = f"／{role}" if role else ""
        line = f"・{label}{role_bit}: {status}"
        if detail and str(r.get("stall_status") or "") not in ("ok", ""):
            line += f"（{detail}）"
        lines.append(line)
    return "\n".join(lines)

REFILL_NAME_RE = re.compile(
    r"S2.*(週次|キュー|再生成|next\s*3|--next)|週次キュー再生成|--next\s*3|"
    r"S9.*(事前|キュー|再生成|--next)|S4.*(キュー|生存|再生成)",
    re.I,
)
REFILL_BODY_RE = re.compile(
    r"(--batch-week|--next\s*3|S2週次キュー再生成|週次バッチ.*再生成|"
    r"s9_precheck|--next\s*2\s*--balanced|S4.*生存キュー)",
    re.I,
)

REFILL_COOLDOWN_HOURS = 12
SEND_RESUME_COOLDOWN_HOURS = 6
# 本線は毎日 09:00「不動産Daily · 本日分」（Hawk/部長 2026-10-20）。
# mark が平日2日以上空いたら #ops 見守り。上書き: state / env JARVIS_VENDOR_STALE_MARK_BUSINESS_DAYS
STALE_MARK_BUSINESS_DAYS_DEFAULT = 2


def stale_marks_threshold_days(state: dict[str, Any] | None = None) -> int:
    raw = (os.environ.get("JARVIS_VENDOR_STALE_MARK_BUSINESS_DAYS") or "").strip()
    if not raw and isinstance(state, dict):
        raw = str(state.get("stale_marks_business_days") or "").strip()
    if raw:
        try:
            n = int(raw)
            if n >= 1:
                return n
        except ValueError:
            pass
    return STALE_MARK_BUSINESS_DAYS_DEFAULT


def now_jst() -> datetime:
    return datetime.now(JST)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_state() -> dict[str, Any]:
    if STATE_PATH.is_file():
        try:
            data = json.loads(STATE_PATH.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                data.setdefault("lanes", {})
                return data
        except Exception:
            pass
    if EXAMPLE_PATH.is_file():
        try:
            data = json.loads(EXAMPLE_PATH.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                data.setdefault("lanes", {})
                return dict(data)
        except Exception:
            pass
    return {"disabled": False, "lanes": {}}


def save_state(state: dict[str, Any]) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    state["last_run_at"] = now_iso()
    STATE_PATH.write_text(
        json.dumps(state, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def parse_iso(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def business_days_between(start: date, end: date) -> int:
    if end <= start:
        return 0
    n = 0
    d = start + timedelta(days=1)
    while d <= end:
        if d.weekday() < 5:
            n += 1
        d += timedelta(days=1)
    return n


def lane_state(state: dict[str, Any], lane: str) -> dict[str, Any]:
    lanes = state.setdefault("lanes", {})
    if not isinstance(lanes, dict):
        lanes = {}
        state["lanes"] = lanes
    cur = lanes.get(lane)
    if not isinstance(cur, dict):
        cur = {}
        # migrate s2 top-level keys
        if lane == "s2":
            for k in ("last_refill_at", "last_ops_alert_at", "last_sync_at"):
                if state.get(k) and not cur.get(k):
                    cur[k] = state[k]
        lanes[lane] = cur
    return cur


def count_followup(vendors: list[Any]) -> int:
    today = date.today()
    n = 0
    for v in vendors:
        if not isinstance(v, dict):
            continue
        st = str(v.get("status") or "")
        if st == "replied":
            n += 1
            continue
        if st != "contacted":
            continue
        ca = str(v.get("contacted_at") or "")[:10]
        if not ca:
            continue
        try:
            sent = date.fromisoformat(ca)
        except ValueError:
            continue
        if (today - sent).days >= 7:
            n += 1
    return n


def contacted_today(vendors: list[Any]) -> int:
    today = date.today().isoformat()
    n = 0
    for v in vendors:
        if not isinstance(v, dict):
            continue
        if str(v.get("status") or "") not in {"contacted", "replied"}:
            continue
        if str(v.get("contacted_at") or "")[:10] == today:
            n += 1
    return n


def last_contacted_date(vendors: list[Any]) -> date | None:
    latest: date | None = None
    for v in vendors:
        if not isinstance(v, dict):
            continue
        if str(v.get("status") or "") not in {"contacted", "replied"}:
            continue
        ca = str(v.get("contacted_at") or "")[:10]
        if not ca:
            continue
        try:
            d = date.fromisoformat(ca)
        except ValueError:
            continue
        if latest is None or d > latest:
            latest = d
    return latest


def assess_s2() -> dict[str, Any]:
    data = load_s2()
    settings = data.get("settings") or {}
    phase, daily = outreach_phase_settings(settings)
    pending = s2_next_pending(limit=max(daily * 7, daily))
    summ = s2_summary(data)
    by = summ.get("by_status") or {}
    vendors = list(data.get("vendors") or [])
    pending_n = int(by.get("pending") or 0) + int(by.get("discovered") or 0)
    return {
        "lane": "s2",
        "phase": phase,
        "daily_limit": daily,
        "queue_ready": len(pending),
        "pending_discovered": pending_n,
        "needs_refill": len(pending) < daily,
        "followup": count_followup(vendors),
        "contacted_today": contacted_today(vendors),
        "last_contacted": (
            last_contacted_date(vendors).isoformat()
            if last_contacted_date(vendors)
            else None
        ),
        "by_status": by,
        "total": summ.get("total") or 0,
        "extra": {},
    }


S9_SENDABLE_CHANNELS = frozenset({"email", "web_form"})


def s9_focus_lane() -> str:
    """S9 の送信対象レーン（ボス方針 2026-10-20「緑区 1 社/日」）。空なら全レーン。"""
    return (os.environ.get("JARVIS_S9_FOCUS_LANE", "midori_caramel") or "").strip()


def s9_sendable_focus(limit: int) -> list[dict[str, Any]]:
    """送信再開・補給で渡す S9 候補。優先レーンのメール／フォームだけ。

    以前は balanced（北区と緑区の混在）で先頭を渡していたため、daily=1 だと台帳順の
    北区（例: 名古屋駅の FC 店）が毎回選ばれ、方針外として送られず mark 停滞 →
    6時間ごとの送信再開で同じ会社が再投入され続けた（2026-10-27 · 通算6回）。
    """
    lane = s9_focus_lane() or None
    return [
        v
        for v in s9_next_pending(limit=max(limit * 10, 10), lane=lane)
        if str(v.get("channel") or "") in S9_SENDABLE_CHANNELS
    ][:limit]


def assess_s9() -> dict[str, Any]:
    data = load_s9()
    settings = data.get("settings") or {}
    daily = int(settings.get("daily_outreach_limit") or 1)
    if daily < 1:
        daily = 1
    # S9 はメール／フォームでしか送らない。電話のみの行を「送信可能」に数えると、緑区が
    # 電話 18 社だけでも queue_ready>0＝正常と判定し、送れないまま止まっていた（2026-10-24）
    items = [
        v
        for v in s9_next_pending(limit=max(daily * 10, 10), balanced=True)
        if str(v.get("channel") or "") in S9_SENDABLE_CHANNELS
    ][: max(daily * 3, daily)]
    # 優先レーン（緑区＝ボス方針 2026-10-20「緑区 1 社/日」）で送れる相手が 0 なら補給が要る
    focus_lane = s9_focus_lane() or "all"
    focus_ready = len(s9_sendable_focus(10))
    summ = s9_summary()
    by = summ.get("by_status") or {}
    vendors = list(data.get("vendors") or [])
    pending_n = int(by.get("pending") or 0) + int(by.get("discovered") or 0)
    return {
        "lane": "s9",
        "phase": None,
        "daily_limit": daily,
        "queue_ready": len(items),
        "focus_lane": focus_lane,
        "focus_ready": focus_ready,
        "pending_discovered": pending_n,
        "needs_refill": len(items) < daily or focus_ready < daily,
        "followup": count_followup(vendors),
        "contacted_today": contacted_today(vendors),
        "last_contacted": (
            last_contacted_date(vendors).isoformat()
            if last_contacted_date(vendors)
            else None
        ),
        "by_status": by,
        "total": summ.get("total") or 0,
        "extra": {
            "alive_ok": summ.get("alive_ok"),
            "vacancy_listing_ok": summ.get("vacancy_listing_ok"),
        },
    }


def assess_s4() -> dict[str, Any]:
    data = load_s4()
    settings = data.get("settings") or {}
    daily = int(settings.get("daily_outreach_limit") or data.get("daily_limit") or 2)
    if daily < 1:
        daily = 2
    items = s4_next_for_contact(limit=max(daily * 3, daily), alive_ok_first=True)
    summ = s4_summary()
    by = summ.get("by_status") or {}
    vendors = [v for v in (data.get("vendors") or []) if isinstance(v, dict)]
    pending_n = int(by.get("pending") or 0) + int(by.get("discovered") or 0)
    alive_queue = len(
        [v for v in items if str(v.get("alive_status") or "") == "ok"]
    )
    return {
        "lane": "s4",
        "phase": None,
        "daily_limit": daily,
        "queue_ready": len(items),
        "pending_discovered": pending_n,
        # S4 は探索中心のため「薄い」＝生存OK連絡候補が日次枠未満
        "needs_refill": alive_queue < daily and pending_n < daily,
        "followup": count_followup(vendors),
        "contacted_today": contacted_today(vendors),
        "last_contacted": (
            last_contacted_date(vendors).isoformat()
            if last_contacted_date(vendors)
            else None
        ),
        "by_status": by,
        "total": summ.get("total") or 0,
        "extra": {"alive_ok": summ.get("alive_ok"), "alive_queue": alive_queue},
    }


ASSESSORS: dict[str, Callable[[], dict[str, Any]]] = {
    "s2": assess_s2,
    "s4": assess_s4,
    "s9": assess_s9,
}


def find_inbox_refill_requests() -> list[Path]:
    try:
        inbox = folder("inbox_from_grok")
    except Exception:
        return []
    hits: list[Path] = []
    for p in list_queue_files(inbox):
        name_hit = bool(REFILL_NAME_RE.search(p.name))
        body_hit = False
        if not name_hit:
            try:
                text = p.read_text(encoding="utf-8", errors="replace")[:4000]
                body_hit = bool(REFILL_BODY_RE.search(text))
            except Exception:
                body_hit = False
        if name_hit or body_hit:
            hits.append(p)
    return hits


def archive_inbox_files(paths: list[Path], *, dry_run: bool) -> list[str]:
    if not paths:
        return []
    try:
        arch = folder("archive")
    except Exception as e:
        print(f"# archive folder missing: {e}", file=sys.stderr)
        return []
    moved: list[str] = []
    for p in paths:
        dest = arch / p.name
        if dest.exists():
            stem, suf = p.stem, p.suffix
            dest = arch / f"{stem}_archived{suf}"
        if dry_run:
            print(f"# dry-run archive: {p.name} → {dest.name}")
            moved.append(p.name)
            continue
        shutil.move(str(p), str(dest))
        moved.append(p.name)
        print(f"📎 archive refill request: {dest}")
    return moved


def bridge_available() -> bool:
    try:
        outbox_dir_for_target("re")
        return True
    except Exception:
        return False


def write_outbox_md(
    *,
    action: str,
    title: str,
    body: str,
    dry_run: bool,
    priority: str = "high",
) -> dict[str, Any]:
    day = now_jst().strftime("%Y-%m-%d")
    hm = now_jst().strftime("%H%M")
    name = f"{day}_{hm}_{sanitize_title(title)}.md"
    try:
        out_dir = outbox_dir_for_target("re")
    except Exception as e:
        return {"ok": False, "error": f"outbox unavailable: {e}"}
    path = out_dir / name
    text = (
        f"# Jarvis → Grok\n"
        f"target: re\n"
        f"priority: {priority}\n"
        f"action: {action}\n"
        f"title: {title}\n"
        f"---\n"
        f"{body}\n"
    )
    if dry_run:
        print(f"# dry-run outbox → {path}")
        print(text[:600] + ("…" if len(text) > 600 else ""))
        return {"ok": True, "dry_run": True, "path": str(path)}
    path.write_text(text, encoding="utf-8")
    print(f"📎 refill outbox: {path}")
    return {"ok": True, "path": str(path)}


def write_s2_refill(*, dry_run: bool) -> dict[str, Any]:
    payload = build_batch_week_payload(batch_days=7)
    kickoff = grok_weekly_kickoff(payload)
    kickoff = kickoff.replace(
        "キュー残り0または不足: 松野へ Jarvis で --batch-week --grok-kickoff 再生成を依頼（Instructions §週次バッチ）",
        "キュー残り0または不足: 部長ボックスへの再依頼は不要。"
        "516／Jarvis の自律 refill（stall runner）を待つ。"
        "2営業日空いたら Slack #ops を確認",
    )
    body = kickoff + "\n\n" + json.dumps(payload, ensure_ascii=False, indent=2)
    batch_id = str(payload.get("batch_id") or "")
    title = f"S2週次バッチ_{batch_id}_自律refill"
    out = write_outbox_md(action="s2_batch", title=title, body=body, dry_run=dry_run)
    out["batch_id"] = batch_id
    out["vendors"] = len(payload.get("vendors") or [])
    return out


def write_s9_refill(*, dry_run: bool) -> dict[str, Any]:
    items = s9_sendable_focus(2)
    if not items:
        return {
            "ok": False,
            "skipped": True,
            "reason": f"s9_precheck: 優先レーン {s9_focus_lane() or 'all'} で送れる候補0件（探索・台帳追加が必要）",
        }
    payload = {
        "ok": True,
        "mode": "s9_precheck",
        "count": len(items),
        "focus_lane": s9_focus_lane() or "all",
        "vendors": items,
        "note": (
            "自律 refill。再依頼不要。"
            "本日分で事前確認メール下書き〜送信（ゲート遵守）。"
        ),
    }
    body = (
        "【S9 事前確認キュー · 自律 refill】\n"
        "優先レーン（既定: 緑区）のメール／フォーム候補のみ。キュー不足時の再依頼 MD は不要"
        "（516／stall runner が補給）。2営業日空いたら Slack #ops。\n\n"
        + json.dumps(payload, ensure_ascii=False, indent=2)
    )
    out = write_outbox_md(
        action="s9_precheck",
        title="S9事前確認_自律refill",
        body=body,
        dry_run=dry_run,
    )
    out["vendors"] = len(items)
    out["batch_id"] = f"s9-{date.today().isoformat()}"
    return out


def write_s4_refill(*, dry_run: bool) -> dict[str, Any]:
    items = s4_next_for_contact(limit=4, alive_ok_first=True)
    payload = {
        "ok": True,
        "mode": "s4_alive_queue",
        "count": len(items),
        "vendors": items,
        "note": (
            "生存OK優先の連絡候補。探索は別途可。"
            "再依頼不要（stall runner 補給）。"
        ),
    }
    body = (
        "【S4 修繕生存キュー · 自律 refill】\n"
        "alive_ok 優先の連絡候補。再依頼 MD は不要。"
        "2営業日空いたら Slack #ops。\n\n"
        + json.dumps(payload, ensure_ascii=False, indent=2)
    )
    out = write_outbox_md(
        action="s4_queue",
        title="S4修繕生存キュー_自律refill",
        body=body,
        dry_run=dry_run,
    )
    out["vendors"] = len(items)
    out["batch_id"] = f"s4-{date.today().isoformat()}"
    return out


REFILLERS: dict[str, Callable[..., dict[str, Any]]] = {
    "s2": write_s2_refill,
    "s4": write_s4_refill,
    "s9": write_s9_refill,
}


def run_sync(script: Path, *, dry_run: bool) -> dict[str, Any]:
    if not script.is_file():
        return {"ok": False, "error": f"missing {script.name}"}
    if dry_run:
        print(f"# dry-run {script.name} --apply")
        return {"ok": True, "dry_run": True}
    cmd = [str(PY if PY.is_file() else sys.executable), str(script), "--apply"]
    r = subprocess.run(
        cmd, cwd=str(REPO), env=os.environ.copy(), capture_output=True, text=True
    )
    if r.stdout:
        print(r.stdout.rstrip())
    if r.returncode != 0:
        if r.stderr:
            print(r.stderr.rstrip(), file=sys.stderr)
        return {"ok": False, "returncode": r.returncode}
    return {"ok": True}


def post_slack(*, channel: str, text: str, dry_run: bool) -> dict[str, Any]:
    if dry_run:
        print(f"# dry-run slack #{channel}\n{text[:800]}")
        return {"ok": True, "dry_run": True, "channel": channel}
    if not SLACK_POST.is_file():
        return {"ok": False, "error": "slack post script missing"}
    cmd = [
        str(PY if PY.is_file() else sys.executable),
        str(SLACK_POST),
        "--channel",
        channel,
        "--text",
        text,
        "--username",
        "516 業者開拓フォロー",
    ]
    r = subprocess.run(
        cmd, cwd=str(REPO), env=os.environ.copy(), capture_output=True, text=True
    )
    if r.stdout:
        print(r.stdout.rstrip())
    if r.returncode != 0:
        if r.stderr:
            print(r.stderr.rstrip(), file=sys.stderr)
        return {"ok": False, "returncode": r.returncode, "channel": channel}
    return {"ok": True, "channel": channel}


def push_sync_meta(key: str, summary: dict[str, Any], *, dry_run: bool) -> None:
    if dry_run:
        print(f"# dry-run sync_meta {key}")
        return
    url = (os.environ.get("JARVIS_SUPABASE_URL") or "").strip()
    skey = (os.environ.get("JARVIS_SUPABASE_SERVICE_ROLE_KEY") or "").strip()
    if not url or not skey:
        print("# sync_meta skip: JARVIS_SUPABASE_* missing", file=sys.stderr)
        return
    try:
        from supabase import create_client

        sb = create_client(url, skey)
        now = now_iso()
        sb.table("sync_meta").upsert(
            {
                "key": key,
                "value": json.dumps(summary, ensure_ascii=False),
                "updated_at": now,
            },
            on_conflict="key",
        ).execute()
        print(f"📎 sync_meta upserted: {key}")
    except Exception as e:
        print(f"# sync_meta upsert failed: {e}", file=sys.stderr)


OPS_ALERT_META_KEY = "vendor_outreach_ops_alert"
OPS_ALERT_COOLDOWN_HOURS = 20


def _sb_client():
    url = (os.environ.get("JARVIS_SUPABASE_URL") or "").strip()
    skey = (os.environ.get("JARVIS_SUPABASE_SERVICE_ROLE_KEY") or "").strip()
    if not url or not skey:
        return None
    try:
        from supabase import create_client

        return create_client(url, skey)
    except Exception as e:
        print(f"# supabase client failed: {e}", file=sys.stderr)
        return None


def fetch_shared_ops_alerts() -> dict[str, str]:
    """Mac と GHA で共有する ops 通知時刻（lane → ISO）。

    GHA は毎回まっさらな state で動くため、ローカル state だけでは
    同じ日に Mac と GHA が同じ #ops を2回出していた（2026-10-26 S9）。
    """
    sb = _sb_client()
    if sb is None:
        return {}
    try:
        res = (
            sb.table("sync_meta")
            .select("value")
            .eq("key", OPS_ALERT_META_KEY)
            .limit(1)
            .execute()
        )
        rows = getattr(res, "data", None) or []
        if not rows:
            return {}
        val = rows[0].get("value")
        data = json.loads(val) if isinstance(val, str) else (val or {})
        return {str(k): str(v) for k, v in data.items() if v} if isinstance(data, dict) else {}
    except Exception as e:
        print(f"# shared ops alert fetch failed: {e}", file=sys.stderr)
        return {}


def remember_shared_ops_alert(lane: str, at_iso: str, *, dry_run: bool) -> None:
    if dry_run:
        return
    cur = fetch_shared_ops_alerts()
    cur[lane] = at_iso
    push_sync_meta(OPS_ALERT_META_KEY, cur, dry_run=False)


def shared_ops_alert_recent(lane: str, shared: dict[str, str]) -> bool:
    last = parse_iso(shared.get(lane))
    return bool(
        last
        and (datetime.now(timezone.utc) - last)
        < timedelta(hours=OPS_ALERT_COOLDOWN_HOURS)
    )


def stale_marks_reason(
    q: dict[str, Any], *, threshold_days: int | None = None
) -> str:
    """mark 停滞の理由文（ops クールダウンとは独立）。空なら停滞なし。

    threshold（既定2平日＝日次運用）を超えたら見守り対象。
    """
    thr = (
        threshold_days
        if threshold_days is not None
        else STALE_MARK_BUSINESS_DAYS_DEFAULT
    )
    last_c = q.get("last_contacted")
    if last_c:
        try:
            lc = date.fromisoformat(str(last_c))
            gap = business_days_between(lc, date.today())
            if gap >= thr and int(q.get("contacted_today") or 0) == 0:
                return (
                    f"最終 contacted から平日{gap}日"
                    f"（閾値{thr}平日）・本日 mark なし（{last_c}）"
                )
        except ValueError:
            return ""
    elif q.get("needs_refill") and (q.get("total") or 0) > 0:
        return "送信可能キュー不足かつ contacted 履歴なし"
    return ""


def should_ops_alert(
    *,
    q: dict[str, Any],
    lst: dict[str, Any],
    bridge_ok: bool,
    skip_refill: bool = False,
    threshold_days: int | None = None,
) -> tuple[bool, str]:
    reasons: list[str] = []
    if not bridge_ok and not skip_refill:
        reasons.append("Mac/Drive ブリッジ未接続（outbox 書けず）")
    if skip_refill and q.get("needs_refill"):
        reasons.append("GHA見守り · キュー不足 · Mac補給待ち")
    stale = stale_marks_reason(q, threshold_days=threshold_days)
    if stale:
        reasons.append(stale)

    last_ops = parse_iso(lst.get("last_ops_alert_at"))
    if last_ops and (datetime.now(timezone.utc) - last_ops) < timedelta(
        hours=OPS_ALERT_COOLDOWN_HOURS
    ):
        # Slack 連投は抑止するが、呼び出し側の stall_status 判定では stale を別途見る
        return False, ""
    if not reasons:
        return False, ""
    return True, "; ".join(reasons)


def _slim_vendor_for_kick(v: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "id",
        "name",
        "area",
        "prefecture",
        "city",
        "url",
        "contact_url",
        "channel",
        "contact_email",
        "email",
        "phone",
        "status",
        "list_region",
        "alive_status",
    )
    return {k: v.get(k) for k in keys if v.get(k) not in (None, "")}


def write_send_resume(lane: str, *, dry_run: bool) -> dict[str, Any]:
    """キュー充足なのに mark 停滞 → 本日分だけ送る kickoff（週次バッチの再投下ではない）。"""
    daily = 3
    vendors: list[dict[str, Any]] = []
    action = f"{lane}_send_resume"
    if lane == "s2":
        data = load_s2()
        settings = data.get("settings") or {}
        _, daily = outreach_phase_settings(settings)
        vendors = [_slim_vendor_for_kick(v) for v in s2_next_pending(limit=daily)]
        how = (
            f"本日分 **{daily}社** を定型テンプレで Web／メール送信し、"
            "各社 `--mark ID --status contacted` を報告。"
            "週次バッチ JSON の再読は不要（キュー先頭から本日分のみ）。"
        )
    elif lane == "s9":
        data = load_s9()
        settings = data.get("settings") or {}
        daily = int(settings.get("daily_outreach_limit") or 2)
        if daily < 1:
            daily = 1
        vendors = [_slim_vendor_for_kick(v) for v in s9_sendable_focus(daily)]
        how = (
            f"本日分 **{daily}社** の事前確認メール（定型）を送信し、"
            "`--mark ID --status contacted` を報告。"
            "キュー補給（s9_precheck）の再投下待ちではない。"
        )
    elif lane == "s4":
        data = load_s4()
        settings = data.get("settings") or {}
        daily = int(settings.get("daily_outreach_limit") or data.get("daily_limit") or 2)
        if daily < 1:
            daily = 2
        vendors = [
            _slim_vendor_for_kick(v)
            for v in s4_next_for_contact(limit=daily, alive_ok_first=True)
        ]
        how = (
            f"本日分 **{daily}社**（生存OK優先）へ定型連絡し、"
            "`--mark` を報告。探索レポートだけでは mark にならない。"
        )
    else:
        return {"ok": False, "error": f"unknown lane {lane}"}

    if not vendors:
        return {
            "ok": False,
            "skipped": True,
            "reason": "send_resume: 本日候補0件",
        }

    payload = {
        "ok": True,
        "mode": "send_resume",
        "lane": lane,
        "day": date.today().isoformat(),
        "daily_limit": daily,
        "count": len(vendors),
        "vendors": vendors,
        "note": (
            "516 stall: mark 停滞のため本日送信を再開。"
            "キューは足りている。週次 refill ではなく **今日の送信＋mark** が本線。"
        ),
    }
    body = (
        f"【{lane.upper()} 送信再開 · 本日分】\n"
        "発信: 516／jarvis_vendor_outreach_stall_runner（stale_marks）。\n"
        f"{how}\n"
        "非定型は松野確認。定型は都度許可不要。\n"
        "完了後: 部長日報に --mark 行を集約。\n\n"
        + json.dumps(payload, ensure_ascii=False, indent=2)
    )
    out = write_outbox_md(
        action=action,
        title=f"{lane.upper()}送信再開_本日分",
        body=body,
        dry_run=dry_run,
        priority="high",
    )
    out["vendors"] = len(vendors)
    out["batch_id"] = f"{lane}-resume-{date.today().isoformat()}"
    out["mode"] = "send_resume"
    return out


def s2_weekly_rollover_due(last_refill_at: str | None, now: datetime | None = None) -> bool:
    """S2 週次バッチ（batch_id=ISO週）が今週分まだ出ていないか。

    部長は batch_id の週単位でキューを持つため、前週バッチの残りが台帳上に残っていても
    月曜以降は「今週のバッチ未着・送信先なし」になる（2026-10-27 W44 未着）。
    キュー不足だけを補給条件にしていたので、週が替わってもバッチが出なかった。
    """
    last = parse_iso(last_refill_at)
    if last is None:
        return True
    cur = (now or now_jst()).astimezone(JST).isocalendar()[:2]
    return last.astimezone(JST).isocalendar()[:2] != cur


def run_lane(
    lane: str,
    *,
    dry: bool,
    force_refill: bool,
    skip_sync: bool,
    skip_refill: bool,
    state: dict[str, Any],
    inbox_hits: list[Path],
    archive_inbox: bool,
) -> dict[str, Any]:
    cfg = LANE_CFG[lane]
    lst = lane_state(state, lane)
    assess = ASSESSORS[lane]
    q = assess()
    bridge_ok = bridge_available()
    label = cfg["label"]
    role = str(cfg.get("role") or "")

    print(
        f"📎 {lane} stall assess: queue_ready={q['queue_ready']} "
        f"daily={q['daily_limit']} needs_refill={q['needs_refill']} "
        f"followup={q['followup']} contacted_today={q['contacted_today']} "
        f"bridge={'ok' if bridge_ok else 'NG'}"
        f"{' skip_refill' if skip_refill else ''}"
    )

    thr = stale_marks_threshold_days(state)
    stale_reason = stale_marks_reason(q, threshold_days=thr)
    is_stale = bool(stale_reason)
    weekly_due = lane == "s2" and s2_weekly_rollover_due(lst.get("last_refill_at"))
    needs_refill = bool(
        force_refill
        or q["needs_refill"]
        or weekly_due
        or (archive_inbox and inbox_hits)
    )
    # キューは足りるが mark 停滞 → 本日送信再開キック（週次 refill とは別）
    needs_send_resume = bool(
        is_stale and not q["needs_refill"] and not force_refill
    )
    refill_result: dict[str, Any] | None = None
    archived: list[str] = []

    if skip_refill:
        refill_result = {
            "ok": True,
            "skipped": True,
            "reason": "skip_refill · Mac補給待ち" if needs_refill else "skip_refill",
        }
        if needs_refill or needs_send_resume:
            print(f"# {lane} refill/resume skipped: GHA/skip_refill（Mac補給待ち）")
    elif needs_refill:
        last_refill = parse_iso(lst.get("last_refill_at"))
        cooldown_ok = True
        if (
            last_refill
            and not force_refill
            and (datetime.now(timezone.utc) - last_refill)
            < timedelta(hours=REFILL_COOLDOWN_HOURS)
        ):
            cooldown_ok = False
            refill_result = {
                "ok": True,
                "skipped": True,
                "reason": f"cooldown {REFILL_COOLDOWN_HOURS}h",
            }
            print(f"# {lane} refill skipped: cooldown")

        if cooldown_ok:
            if not bridge_ok:
                refill_result = {
                    "ok": False,
                    "skipped": True,
                    "reason": "Mac未接続・outbox不可",
                }
            else:
                refill_result = REFILLERS[lane](dry_run=dry)
                if refill_result.get("ok") and not dry:
                    lst["last_refill_at"] = now_iso()
                    if lane == "s2":
                        state["last_refill_at"] = lst["last_refill_at"]
                if archive_inbox and inbox_hits:
                    archived = archive_inbox_files(inbox_hits, dry_run=dry)
    elif needs_send_resume:
        last_resume = parse_iso(lst.get("last_send_resume_at"))
        cooldown_ok = True
        if (
            last_resume
            and (datetime.now(timezone.utc) - last_resume)
            < timedelta(hours=SEND_RESUME_COOLDOWN_HOURS)
        ):
            cooldown_ok = False
            refill_result = {
                "ok": True,
                "skipped": True,
                "reason": f"send_resume cooldown {SEND_RESUME_COOLDOWN_HOURS}h",
                "mode": "send_resume",
            }
            print(f"# {lane} send_resume skipped: cooldown")
        elif not bridge_ok:
            refill_result = {
                "ok": False,
                "skipped": True,
                "reason": "Mac未接続・送信再開キック不可",
                "mode": "send_resume",
            }
        else:
            print(f"# {lane} send_resume: {stale_reason}")
            refill_result = write_send_resume(lane, dry_run=dry)
            if refill_result.get("ok") and not dry:
                lst["last_send_resume_at"] = now_iso()
    else:
        refill_result = {"ok": True, "skipped": True, "reason": "queue_ok"}

    sync_ok: bool | None = None
    if not skip_sync:
        if not cfg["list_path"].is_file():
            print(f"# {lane} YAML missing: {cfg['list_path']}", file=sys.stderr)
            sync_ok = False
        else:
            sr = run_sync(cfg["sync"], dry_run=dry)
            sync_ok = bool(sr.get("ok"))
            if sync_ok and not dry:
                lst["last_sync_at"] = now_iso()
                if lane == "s2":
                    state["last_sync_at"] = lst["last_sync_at"]

    ops_needed, ops_reason = should_ops_alert(
        q=q,
        lst=lst,
        bridge_ok=bridge_ok,
        skip_refill=skip_refill,
        threshold_days=thr,
    )
    if refill_result and not refill_result.get("ok") and not refill_result.get("skipped"):
        ops_needed = True
        ops_reason = ops_reason or str(refill_result.get("error") or "refill failed")
    if not bridge_ok and (needs_refill or needs_send_resume) and not skip_refill:
        ops_needed = True
        ops_reason = ops_reason or "Mac未接続・補給スキップ"

    # stall_status は ops クールダウンと独立（クールダウン中に ok と誤表示しない）
    stall_status = "ok"
    if not bridge_ok and not skip_refill:
        stall_status = "bridge_down"
    elif q["needs_refill"]:
        stall_status = "needs_refill"
    elif is_stale:
        stall_status = "stale_marks"

    meta = {
        "at": now_iso(),
        "day": now_jst().strftime("%Y-%m-%d"),
        "lane": lane,
        "stall_status": stall_status,
        "phase": q.get("phase"),
        "daily_limit": q["daily_limit"],
        "queue_ready": q["queue_ready"],
        "pending_discovered": q["pending_discovered"],
        "followup": q["followup"],
        "contacted_today": q["contacted_today"],
        "last_contacted": q["last_contacted"],
        "stale_marks_business_days": thr,
        "last_refill_at": lst.get("last_refill_at"),
        "last_sync_at": lst.get("last_sync_at"),
        "bridge_ok": bridge_ok,
        "by_status": q["by_status"],
        "kurashift_url": cfg["url"],
        "extra": q.get("extra") or {},
        "refill": {
            "skipped": bool((refill_result or {}).get("skipped")),
            "ok": bool((refill_result or {}).get("ok")),
            "batch_id": (refill_result or {}).get("batch_id"),
            "reason": (refill_result or {}).get("reason")
            or (refill_result or {}).get("error"),
        },
    }
    push_sync_meta(cfg["meta_key"], meta, dry_run=dry)

    return {
        "lane": lane,
        "label": label,
        "role": role,
        "q": q,
        "meta": meta,
        "refill": refill_result,
        "sync_ok": sync_ok,
        "ops_needed": ops_needed,
        "ops_reason": ops_reason,
        "stall_status": stall_status,
        "archived": archived,
        "url": cfg["url"],
        "lst": lst,
    }


_STALL_STATUS_JA = {
    "ok": "正常",
    "needs_refill": "キュー補給待ち",
    "bridge_down": "Mac未接続",
    "stale_marks": "送信停滞（markなし）",
}


def _stall_status_ja(status: str) -> str:
    return _STALL_STATUS_JA.get(status, status or "—")


def _week_period_label(state: dict[str, Any]) -> str:
    """週次レポートの期間表示（最終週次〜今日、無ければ直近7日）。"""
    today = now_jst().date()
    raw = (
        state.get("last_weekly_report_at")
        or state.get("last_daily_report_at")
        or ""
    )
    start: date | None = None
    if raw:
        try:
            start = date.fromisoformat(str(raw)[:10]) + timedelta(days=1)
        except ValueError:
            start = None
    if start is None or start > today:
        start = today - timedelta(days=6)
    return f"{start.isoformat()} 〜 {today.isoformat()}"


def all_lanes_healthy(results: list[dict[str, Any]]) -> bool:
    if not results:
        return False
    return all(r.get("stall_status") == "ok" and not r.get("ops_needed") for r in results)


def should_post_weekly_report(
    state: dict[str, Any],
    results: list[dict[str, Any]],
    *,
    force: bool = False,
) -> tuple[bool, str]:
    """healthy なときだけ週次 #report。月曜 or 最終から7日以上。"""
    if force:
        return True, "force"
    if not all_lanes_healthy(results):
        return False, "not_healthy（異常は #ops のみ）"
    today = now_jst().date()
    last_raw = (
        state.get("last_weekly_report_at")
        or state.get("last_daily_report_at")
        or ""
    )
    last_d: date | None = None
    if last_raw:
        try:
            last_d = date.fromisoformat(str(last_raw)[:10])
        except ValueError:
            last_d = None
    if last_d == today:
        return False, "already_sent_today"
    if last_d is None:
        return True, "first"
    if (today - last_d).days >= 7:
        return True, "elapsed_7d"
    # 月曜（weekday 0）かつ最終が前週以前
    if today.weekday() == 0 and last_d < today:
        return True, "monday"
    return False, f"wait（last={last_d.isoformat()} weekday={today.weekday()}）"


def build_support_weekly_report(
    results: list[dict[str, Any]], *, state: dict[str, Any] | None = None
) -> str:
    """Grokサポート見守り・週次サマリ（レーン擬似表）。"""
    st = state or {}
    period = _week_period_label(st)
    lines = [
        "[516 業者開拓フォロー] *Grokサポート見守り｜業者開拓*",
        "発信: 516 業者開拓フォロー（開拓の送信・文案は Grok S2/S4/S9）。",
        f"期間: {period}",
        "",
    ]
    for r in results:
        q = r["q"]
        by = q.get("by_status") or {}
        refill = r.get("refill") or {}
        if refill.get("skipped"):
            refill_line = f"skip({refill.get('reason') or '—'})"
        elif refill.get("ok"):
            refill_line = f"ok vendors={refill.get('vendors')}"
        else:
            refill_line = f"fail:{refill.get('error') or '—'}"
        sync_line = (
            "OK"
            if r.get("sync_ok") is True
            else ("失敗" if r.get("sync_ok") is False else "—")
        )
        status_ja = _stall_status_ja(str(r.get("stall_status") or ""))
        lines.extend(
            [
                f"{format_lane_heading(r)}  状態: {status_ja}",
                f"・接触 {q.get('contacted_today', 0)}／"
                f"キュー残 {q.get('pending_discovered', 0)}"
                f"（先頭{q.get('queue_ready', 0)}/枠{q.get('daily_limit', 0)}）／"
                f"要フォロー {q.get('followup', 0)}",
                f"・未送{by.get('pending', 0)}／探索{by.get('discovered', 0)}／"
                f"済{by.get('contacted', 0)}／返信{by.get('replied', 0)}",
                f"・refill {refill_line} · sync {sync_line}",
                f"・<{r['url']}|UIを開く>",
                "",
            ]
        )
    lines.append("次: 異常時は #ops。詳細は KURASHIFT 各レーン。")
    return "\n".join(lines).rstrip()


def build_multi_report(results: list[dict[str, Any]], *, state: dict[str, Any] | None = None) -> str:
    """後方互換エイリアス → 週次サポート報告。"""
    return build_support_weekly_report(results, state=state)


def _short_date(d: Any) -> str:
    t = str(d or "")
    try:
        x = date.fromisoformat(t[:10])
        return f"{x.month}/{x.day}"
    except ValueError:
        return t or "—"


def build_ops_alert(r: dict[str, Any]) -> str:
    """#ops 要確認（iPhone: 先頭1行で係とレーン、本文4〜5行）。"""
    lane = r.get("lane") or "?"
    q = r.get("q") or {}
    stall = str(r.get("stall_status") or "")
    refill = r.get("refill") or {}
    if stall == "needs_refill" or q.get("needs_refill"):
        what = "送信できる候補が足りません"
        remedy = f"Macで `--apply --lane {lane} --force-refill`"
    elif stall == "stale_marks":
        what = f"送信が止まっています（最終 {_short_date(q.get('last_contacted'))}）"
        if refill.get("mode") == "send_resume" and refill.get("ok") and not refill.get("skipped"):
            remedy = "再開キック済。Grokが本日分を送信＋`--mark`"
        else:
            remedy = "Grokが本日分を送信＋`--mark`"
    elif stall == "bridge_down":
        what = "Mac／Drive につながっていません"
        remedy = "復旧後に `--apply --lane all`"
    else:
        what = str(r.get("ops_reason") or "要確認")
        remedy = f"`--apply --lane {lane}`"
    label = str(r.get("label") or lane).strip()
    return "\n".join(
        [
            f"【ops】516 業者開拓フォロー｜{label}",
            what,
            f"キュー {q.get('pending_discovered')}（送信可能 {q.get('queue_ready')}）",
            f"次: {remedy}",
            f"<{r.get('url')}|UIを開く>",
        ]
    )


def parse_lanes(raw: str) -> list[str]:
    s = (raw or "all").strip().lower()
    if s in ("all", "*", "s2,s4,s9"):
        return ["s2", "s4", "s9"]
    parts = [p.strip() for p in s.split(",") if p.strip()]
    out: list[str] = []
    for p in parts:
        if p not in LANE_CFG:
            raise SystemExit(f"unknown lane: {p} (s2|s4|s9|all)")
        if p not in out:
            out.append(p)
    return out or ["s2"]


def run(*, args: argparse.Namespace) -> int:
    state = load_state()
    if state.get("disabled") and not args.force_refill:
        print("📎 vendor_outreach_stall: disabled（state.disabled=true）")
        return 0
    if os.environ.get("JARVIS_VENDOR_OUTREACH_STALL_DISABLE") == "1" and not args.force_refill:
        print("📎 vendor_outreach_stall: disabled（env）")
        return 0

    dry = bool(args.dry_run) and not args.apply
    if not args.apply and not args.dry_run:
        dry = True

    lanes = parse_lanes(args.lane)
    skip_refill = bool(args.skip_refill) or (
        (os.environ.get("JARVIS_VENDOR_OUTREACH_STALL_SKIP_REFILL") or "").strip()
        in ("1", "true", "yes", "on")
    )
    # GHA 見守りでは Drive outbox を書かない（inbox も触らない）
    inbox_hits = (
        []
        if skip_refill
        else (find_inbox_refill_requests() if "s2" in lanes else [])
    )
    results: list[dict[str, Any]] = []
    shared_alerts: dict[str, str] | None = None

    for i, lane in enumerate(lanes):
        if not LANE_CFG[lane]["list_path"].is_file() and lane != "s2":
            print(f"# skip {lane}: YAML missing", file=sys.stderr)
            continue
        if lane == "s2" and not S2_LIST.is_file():
            print(f"❌ S2 YAML なし: {S2_LIST}", file=sys.stderr)
            if len(lanes) == 1:
                return 1
            continue
        r = run_lane(
            lane,
            dry=dry,
            force_refill=bool(args.force_refill) and not skip_refill,
            skip_sync=bool(args.skip_sync),
            skip_refill=skip_refill,
            state=state,
            inbox_hits=inbox_hits,
            archive_inbox=(lane == "s2" and i == 0 and not skip_refill),
        )
        results.append(r)

        if r["ops_needed"] and (args.apply or args.dry_run or args.ops_alert):
            if shared_alerts is None:
                shared_alerts = fetch_shared_ops_alerts()
            if shared_ops_alert_recent(lane, shared_alerts):
                print(f"# {lane} ops alert skipped: 共有クールダウン {OPS_ALERT_COOLDOWN_HOURS}h")
                r["ops_needed"] = False
                continue
            ops_text = build_ops_alert(r)
            pr = post_slack(channel="ops", text=ops_text, dry_run=dry)
            if pr.get("ok") and not dry:
                r["lst"]["last_ops_alert_at"] = now_iso()
                remember_shared_ops_alert(lane, r["lst"]["last_ops_alert_at"], dry_run=dry)
                shared_alerts[lane] = r["lst"]["last_ops_alert_at"]
                if lane == "s2":
                    state["last_ops_alert_at"] = r["lst"]["last_ops_alert_at"]

    # evening／daily-report: 見回りは毎日。#report は週次ゲート（healthy のみ）
    do_weekly_slot = bool(args.daily_report or args.evening)
    if do_weekly_slot and results:
        ok_post, reason = should_post_weekly_report(
            state, results, force=bool(args.force_report)
        )
        if not ok_post:
            print(f"# weekly report skipped: {reason}")
        else:
            text = build_support_weekly_report(results, state=state)
            pr = post_slack(channel="report", text=text, dry_run=dry)
            if pr.get("ok") and not dry:
                state["last_weekly_report_at"] = now_iso()
                # 互換: 旧キーも更新
                state["last_daily_report_at"] = state["last_weekly_report_at"]

    state["last_result"] = {
        "lanes": {
            r["lane"]: {
                "stall_status": r["stall_status"],
                "needs_refill": r["q"]["needs_refill"],
                "queue_ready": r["q"]["queue_ready"],
                "ops_needed": r["ops_needed"],
                "ops_reason": r["ops_reason"],
            }
            for r in results
        }
    }
    if not dry:
        save_state(state)
    else:
        print("# dry-run: state not saved")

    statuses = ",".join(f"{r['lane']}={r['stall_status']}" for r in results) or "none"
    print(f"📎 vendor_outreach_stall done: {statuses}")
    if args.json:
        print(
            json.dumps(
                {"results": [{"lane": r["lane"], "meta": r["meta"]} for r in results]},
                ensure_ascii=False,
                indent=2,
            )
        )
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true", help="書込・投稿なし（既定）")
    ap.add_argument("--apply", action="store_true", help="outbox / sync / Slack を実行")
    ap.add_argument(
        "--lane",
        default="all",
        help="s2 | s4 | s9 | all（カンマ可）。既定 all",
    )
    ap.add_argument("--force-refill", action="store_true", help="キューに余裕があっても再投入")
    ap.add_argument(
        "--skip-refill",
        action="store_true",
        help="outbox 補給をしない（GHA見守り用。env JARVIS_VENDOR_OUTREACH_STALL_SKIP_REFILL=1 でも可）",
    )
    ap.add_argument(
        "--daily-report",
        action="store_true",
        help="夕方枠の別名。見回り後、healthy なら週次 #report を検討",
    )
    ap.add_argument(
        "--evening",
        action="store_true",
        help="夕方枠（見回り＋週次 #report ゲート。異常は #ops）",
    )
    ap.add_argument(
        "--force-report",
        action="store_true",
        help="週次ゲートを無視して #report を投稿（デバッグ）",
    )
    ap.add_argument("--ops-alert", action="store_true", help="条件時に #ops")
    ap.add_argument("--skip-sync", action="store_true", help="vendor_sync をしない")
    ap.add_argument("--json", action="store_true", help="詳細 JSON を stdout")
    args = ap.parse_args()
    return run(args=args)


if __name__ == "__main__":
    raise SystemExit(main())
