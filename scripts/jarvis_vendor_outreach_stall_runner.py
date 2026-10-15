#!/usr/bin/env python3
"""S2 業者開拓 — キュー枯渇・未着を検知し、自律 refill / sync / Slack 報告。

対外 Web 送信はしない（Grok／人が送る）。Mac 側の補給・投影・報告だけ。

  cd ~/git-repos && set -a && source .env.jarvis_private && set +a
  ~/selenium_env/venv/bin/python scripts/jarvis_vendor_outreach_stall_runner.py --dry-run
  ~/selenium_env/venv/bin/python scripts/jarvis_vendor_outreach_stall_runner.py --apply
  ~/selenium_env/venv/bin/python scripts/jarvis_vendor_outreach_stall_runner.py --apply --force-refill
  ~/selenium_env/venv/bin/python scripts/jarvis_vendor_outreach_stall_runner.py --apply --daily-report
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
from typing import Any
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
    LIST_PATH,
    build_batch_week_payload,
    grok_weekly_kickoff,
    load_list,
    next_pending,
    outreach_phase_settings,
    summary as vendor_summary,
)

JST = ZoneInfo("Asia/Tokyo")
STATE_PATH = REPO / ".jarvis_state" / "vendor_outreach_stall.json"
EXAMPLE_PATH = REPO / ".jarvis_state" / "vendor_outreach_stall.example.json"
PY = Path.home() / "selenium_env" / "venv" / "bin" / "python"
VENDOR_SYNC = REPO / "scripts" / "jarvis_kurashift_vendor_sync.py"
SLACK_POST = REPO / "scripts" / "jarvis_slack_webhook_post.py"
KURASHIFT_VENDORS_URL = "https://jarvis-trade-desk.vercel.app/realestate/vendors"
SYNC_META_KEY = "vendor_outreach_stall"

# inbox ファイル名／本文に出る再生成依頼のシグナル
REFILL_NAME_RE = re.compile(
    r"S2.*(週次|キュー|再生成|next\s*3|--next)|週次キュー再生成|--next\s*3",
    re.I,
)
REFILL_BODY_RE = re.compile(
    r"(--batch-week|--next\s*3|S2週次キュー再生成|週次バッチ.*再生成)",
    re.I,
)

# 同じ日に二重 refill しない（force 除く）
REFILL_COOLDOWN_HOURS = 12
# contacted/mark が無い日が続いたら #ops
STALE_MARK_BUSINESS_DAYS = 2


def now_jst() -> datetime:
    return datetime.now(JST)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_state() -> dict[str, Any]:
    if STATE_PATH.is_file():
        try:
            data = json.loads(STATE_PATH.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
        except Exception:
            pass
    if EXAMPLE_PATH.is_file():
        try:
            data = json.loads(EXAMPLE_PATH.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return dict(data)
        except Exception:
            pass
    return {"disabled": False}


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
    """start 翌日〜end までの平日数（土日のみ除外）。"""
    if end <= start:
        return 0
    n = 0
    d = start + timedelta(days=1)
    while d <= end:
        if d.weekday() < 5:
            n += 1
        d += timedelta(days=1)
    return n


def count_followup(data: dict[str, Any]) -> int:
    today = date.today()
    n = 0
    for v in data.get("vendors") or []:
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


def contacted_today(data: dict[str, Any]) -> int:
    today = date.today().isoformat()
    n = 0
    for v in data.get("vendors") or []:
        if not isinstance(v, dict):
            continue
        if str(v.get("status") or "") not in {"contacted", "replied"}:
            continue
        ca = str(v.get("contacted_at") or "")[:10]
        if ca == today:
            n += 1
    return n


def last_contacted_date(data: dict[str, Any]) -> date | None:
    latest: date | None = None
    for v in data.get("vendors") or []:
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


def assess_queue(data: dict[str, Any]) -> dict[str, Any]:
    settings = data.get("settings") or {}
    phase, daily = outreach_phase_settings(settings)
    pending = next_pending(limit=max(daily * 7, daily))
    queue_n = len(pending)
    summ = vendor_summary(data)
    by = summ.get("by_status") or {}
    pending_n = int(by.get("pending") or 0) + int(by.get("discovered") or 0)
    return {
        "phase": phase,
        "daily_limit": daily,
        "queue_ready": queue_n,
        "pending_discovered": pending_n,
        "needs_refill": queue_n < daily,
        "followup": count_followup(data),
        "contacted_today": contacted_today(data),
        "last_contacted": (
            last_contacted_date(data).isoformat() if last_contacted_date(data) else None
        ),
        "by_status": by,
        "total": summ.get("total") or 0,
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


def write_s2_batch_outbox(*, dry_run: bool) -> dict[str, Any]:
    payload = build_batch_week_payload(batch_days=7)
    kickoff = grok_weekly_kickoff(payload)
    # 自律 refill 後は再依頼ループを止める文言に差し替え
    kickoff = kickoff.replace(
        "キュー残り0または不足: 松野へ Jarvis で --batch-week --grok-kickoff 再生成を依頼（Instructions §週次バッチ）",
        "キュー残り0または不足: 部長ボックスへの再依頼は不要。"
        "516／Jarvis の自律 refill（stall runner）を待つ。"
        "2営業日空いたら Slack #ops を確認",
    )
    body = kickoff + "\n\n" + json.dumps(payload, ensure_ascii=False, indent=2)
    batch_id = str(payload.get("batch_id") or iso_week_fallback())
    title = f"S2週次バッチ_{batch_id}_自律refill"
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
        f"priority: high\n"
        f"action: s2_batch\n"
        f"title: {title}\n"
        f"---\n"
        f"{body}\n"
    )
    if dry_run:
        print(f"# dry-run outbox → {path}")
        print(text[:800] + ("…" if len(text) > 800 else ""))
        return {
            "ok": True,
            "dry_run": True,
            "path": str(path),
            "batch_id": batch_id,
            "vendors": len(payload.get("vendors") or []),
        }
    path.write_text(text, encoding="utf-8")
    print(f"📎 S2 refill outbox: {path} vendors={len(payload.get('vendors') or [])}")
    return {
        "ok": True,
        "path": str(path),
        "batch_id": batch_id,
        "vendors": len(payload.get("vendors") or []),
    }


def iso_week_fallback() -> str:
    iso = date.today().isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


def run_vendor_sync(*, dry_run: bool) -> dict[str, Any]:
    if not VENDOR_SYNC.is_file():
        return {"ok": False, "error": "vendor_sync missing"}
    if dry_run:
        print("# dry-run vendor_sync --apply")
        return {"ok": True, "dry_run": True}
    cmd = [str(PY if PY.is_file() else sys.executable), str(VENDOR_SYNC), "--apply"]
    env = os.environ.copy()
    r = subprocess.run(cmd, cwd=str(REPO), env=env, capture_output=True, text=True)
    if r.stdout:
        print(r.stdout.rstrip())
    if r.returncode != 0:
        if r.stderr:
            print(r.stderr.rstrip(), file=sys.stderr)
        return {"ok": False, "returncode": r.returncode}
    return {"ok": True}


def post_slack(*, channel: str, text: str, dry_run: bool) -> dict[str, Any]:
    if dry_run:
        print(f"# dry-run slack #{channel}\n{text[:600]}")
        return {"ok": True, "dry_run": True, "channel": channel}
    if not SLACK_POST.is_file():
        return {"ok": False, "error": "slack post script missing"}
    # env 必須
    cmd = [
        str(PY if PY.is_file() else sys.executable),
        str(SLACK_POST),
        "--channel",
        channel,
        "--text",
        text,
        "--username",
        "516業者開拓フォロー係",
    ]
    r = subprocess.run(cmd, cwd=str(REPO), env=os.environ.copy(), capture_output=True, text=True)
    if r.stdout:
        print(r.stdout.rstrip())
    if r.returncode != 0:
        if r.stderr:
            print(r.stderr.rstrip(), file=sys.stderr)
        return {"ok": False, "returncode": r.returncode, "channel": channel}
    return {"ok": True, "channel": channel}


def push_sync_meta(summary: dict[str, Any], *, dry_run: bool) -> None:
    if dry_run:
        print(f"# dry-run sync_meta {SYNC_META_KEY}")
        return
    url = (os.environ.get("JARVIS_SUPABASE_URL") or "").strip()
    key = (os.environ.get("JARVIS_SUPABASE_SERVICE_ROLE_KEY") or "").strip()
    if not url or not key:
        print("# sync_meta skip: JARVIS_SUPABASE_* missing", file=sys.stderr)
        return
    try:
        from supabase import create_client

        sb = create_client(url, key)
        now = now_iso()
        sb.table("sync_meta").upsert(
            {
                "key": SYNC_META_KEY,
                "value": json.dumps(summary, ensure_ascii=False),
                "updated_at": now,
            },
            on_conflict="key",
        ).execute()
        print(f"📎 sync_meta upserted: {SYNC_META_KEY}")
    except Exception as e:
        print(f"# sync_meta upsert failed: {e}", file=sys.stderr)


def should_ops_alert(
    *,
    q: dict[str, Any],
    state: dict[str, Any],
    bridge_ok: bool,
) -> tuple[bool, str]:
    reasons: list[str] = []
    if not bridge_ok:
        reasons.append("Mac/Drive ブリッジ未接続（outbox 書けず）")
    last_c = q.get("last_contacted")
    if last_c:
        try:
            lc = date.fromisoformat(str(last_c))
            gap = business_days_between(lc, date.today())
            if gap >= STALE_MARK_BUSINESS_DAYS and q.get("contacted_today", 0) == 0:
                reasons.append(
                    f"最終 contacted から平日{gap}日・本日 mark なし（{last_c}）"
                )
        except ValueError:
            pass
    else:
        # 一度も contacted が無いがキューはある → 初回待機はアラートしない
        if q.get("needs_refill") and (q.get("total") or 0) > 0:
            reasons.append("送信可能キュー不足かつ contacted 履歴なし")

    last_ops = parse_iso(state.get("last_ops_alert_at"))
    if last_ops and (datetime.now(timezone.utc) - last_ops) < timedelta(hours=20):
        return False, ""
    if not reasons:
        return False, ""
    return True, "; ".join(reasons)


def build_daily_report_text(
    *,
    q: dict[str, Any],
    refill: dict[str, Any] | None,
    sync_ok: bool | None,
    archived: list[str],
    stall_status: str,
) -> str:
    day = now_jst().strftime("%Y-%m-%d")
    refill_line = "不要"
    if refill:
        if refill.get("skipped"):
            refill_line = f"スキップ（{refill.get('reason') or '—'}）"
        elif refill.get("ok"):
            refill_line = (
                f"実施 batch={refill.get('batch_id')} "
                f"vendors={refill.get('vendors')} "
                f"{'(dry-run)' if refill.get('dry_run') else ''}"
            ).strip()
        else:
            refill_line = f"失敗: {refill.get('error') or refill}"
    sync_line = "—（未実行）"
    if sync_ok is True:
        sync_line = "OK"
    elif sync_ok is False:
        sync_line = "失敗"

    by = q.get("by_status") or {}
    lines = [
        f"*S2業者開拓* {day}",
        f"・本日送信相当（contacted 当日）: {q.get('contacted_today', 0)}",
        f"・キュー残（pending+discovered）: {q.get('pending_discovered', 0)} "
        f"（送信可能先頭 {q.get('queue_ready', 0)} / 日次枠 {q.get('daily_limit', 3)}）",
        f"・要フォロー: {q.get('followup', 0)}",
        f"・status: 未送信 {by.get('pending', 0)} · 探索 {by.get('discovered', 0)} · "
        f"送信済 {by.get('contacted', 0)} · 返信 {by.get('replied', 0)}",
        f"・自律 refill: {refill_line}",
        f"・vendor_sync: {sync_line}",
        f"・stall: {stall_status}",
    ]
    if archived:
        lines.append(f"・inbox 再生成依頼を archive: {len(archived)} 件")
    lines.append(f"・KURASHIFT: {KURASHIFT_VENDORS_URL}")
    return "\n".join(lines)


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

    if not LIST_PATH.is_file():
        print(f"❌ YAML なし: {LIST_PATH}", file=sys.stderr)
        return 1

    data = load_list()
    q = assess_queue(data)
    inbox_hits = find_inbox_refill_requests()
    bridge_ok = bridge_available()

    print(
        f"📎 S2 stall assess: queue_ready={q['queue_ready']} "
        f"daily={q['daily_limit']} needs_refill={q['needs_refill']} "
        f"followup={q['followup']} contacted_today={q['contacted_today']} "
        f"inbox_refill={len(inbox_hits)} bridge={'ok' if bridge_ok else 'NG'}"
    )

    needs_refill = bool(args.force_refill or q["needs_refill"] or inbox_hits)
    refill_result: dict[str, Any] | None = None
    archived: list[str] = []

    if needs_refill:
        last_refill = parse_iso(state.get("last_refill_at"))
        cooldown_ok = True
        if (
            last_refill
            and not args.force_refill
            and (datetime.now(timezone.utc) - last_refill)
            < timedelta(hours=REFILL_COOLDOWN_HOURS)
        ):
            cooldown_ok = False
            refill_result = {
                "ok": True,
                "skipped": True,
                "reason": f"cooldown {REFILL_COOLDOWN_HOURS}h",
            }
            print(f"# refill skipped: cooldown since {state.get('last_refill_at')}")

        if cooldown_ok:
            if not bridge_ok:
                refill_result = {
                    "ok": False,
                    "skipped": True,
                    "reason": "Mac未接続・outbox不可",
                }
                print("# refill skipped: bridge unavailable", file=sys.stderr)
            else:
                refill_result = write_s2_batch_outbox(dry_run=dry)
                if refill_result.get("ok") and not dry:
                    state["last_refill_at"] = now_iso()
                if inbox_hits:
                    archived = archive_inbox_files(inbox_hits, dry_run=dry)
    else:
        refill_result = {"ok": True, "skipped": True, "reason": "queue_ok"}

    sync_ok: bool | None = None
    if args.skip_sync:
        sync_ok = None
    else:
        # YAML がある日は投影を更新（朝／夕方の定例）
        sr = run_vendor_sync(dry_run=dry)
        sync_ok = bool(sr.get("ok"))
        if sync_ok and not dry:
            state["last_sync_at"] = now_iso()

    ops_needed, ops_reason = should_ops_alert(
        q=q, state=state, bridge_ok=bridge_ok
    )
    # refill 失敗かつ bridge NG は必ず ops
    if refill_result and not refill_result.get("ok") and not refill_result.get("skipped"):
        ops_needed = True
        ops_reason = ops_reason or str(refill_result.get("error") or "refill failed")
    if not bridge_ok and needs_refill:
        ops_needed = True
        ops_reason = ops_reason or "Mac未接続・補給スキップ"

    stall_status = "ok"
    if not bridge_ok:
        stall_status = "bridge_down"
    elif q["needs_refill"]:
        stall_status = "needs_refill"
    elif ops_needed:
        stall_status = "stale_marks"

    meta = {
        "at": now_iso(),
        "day": now_jst().strftime("%Y-%m-%d"),
        "stall_status": stall_status,
        "phase": q["phase"],
        "daily_limit": q["daily_limit"],
        "queue_ready": q["queue_ready"],
        "pending_discovered": q["pending_discovered"],
        "followup": q["followup"],
        "contacted_today": q["contacted_today"],
        "last_contacted": q["last_contacted"],
        "last_refill_at": state.get("last_refill_at"),
        "last_sync_at": state.get("last_sync_at"),
        "bridge_ok": bridge_ok,
        "by_status": q["by_status"],
        "kurashift_url": KURASHIFT_VENDORS_URL,
        "refill": {
            "skipped": bool((refill_result or {}).get("skipped")),
            "ok": bool((refill_result or {}).get("ok")),
            "batch_id": (refill_result or {}).get("batch_id"),
            "reason": (refill_result or {}).get("reason")
            or (refill_result or {}).get("error"),
        },
    }
    push_sync_meta(meta, dry_run=dry)

    do_daily = bool(args.daily_report or args.evening)
    if do_daily:
        last_daily = str(state.get("last_daily_report_at") or "")[:10]
        today = now_jst().strftime("%Y-%m-%d")
        if last_daily == today and not args.force_report and not dry:
            print("# daily report skipped: already sent today")
        else:
            text = build_daily_report_text(
                q=q,
                refill=refill_result,
                sync_ok=sync_ok,
                archived=archived,
                stall_status=stall_status,
            )
            pr = post_slack(channel="report", text=text, dry_run=dry)
            if pr.get("ok") and not dry:
                state["last_daily_report_at"] = now_iso()

    if ops_needed and (args.apply or args.dry_run or args.ops_alert):
        ops_text = (
            f"*S2業者開拓 · 連携障害*\n"
            f"・理由: {ops_reason}\n"
            f"・キュー残: {q['pending_discovered']}（送信可能 {q['queue_ready']}）\n"
            f"・最終 contacted: {q.get('last_contacted') or '—'}\n"
            f"・bridge: {'ok' if bridge_ok else 'NG'}\n"
            f"・UI: {KURASHIFT_VENDORS_URL}\n"
            f"・処置: Mac 接続後に "
            f"`jarvis_vendor_outreach_stall_runner.py --apply --force-refill`"
        )
        pr = post_slack(channel="ops", text=ops_text, dry_run=dry)
        if pr.get("ok") and not dry:
            state["last_ops_alert_at"] = now_iso()

    state["last_result"] = {
        "stall_status": stall_status,
        "needs_refill": q["needs_refill"],
        "queue_ready": q["queue_ready"],
        "refill": refill_result,
        "sync_ok": sync_ok,
        "ops_needed": ops_needed,
        "ops_reason": ops_reason,
        "archived": archived,
    }
    if not dry:
        save_state(state)
    else:
        print("# dry-run: state not saved")

    print(
        "📎 vendor_outreach_stall done: "
        f"status={stall_status} refill="
        f"{(refill_result or {}).get('skipped') and 'skip' or (refill_result or {}).get('ok')}"
    )
    if args.json:
        print(json.dumps({"queue": q, "meta": meta, "state": state.get("last_result")}, ensure_ascii=False, indent=2))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true", help="書込・投稿なし（既定）")
    ap.add_argument("--apply", action="store_true", help="outbox / sync / Slack を実行")
    ap.add_argument("--force-refill", action="store_true", help="キューに余裕があっても週次 JSON を再投入")
    ap.add_argument("--daily-report", action="store_true", help="Slack #report に日次サマリ")
    ap.add_argument(
        "--evening",
        action="store_true",
        help="夕方枠（= --daily-report）。部長日報帯向け",
    )
    ap.add_argument("--force-report", action="store_true", help="同日再投稿を許可")
    ap.add_argument("--ops-alert", action="store_true", help="条件時に #ops（apply 時は自動）")
    ap.add_argument("--skip-sync", action="store_true", help="vendor_sync をしない")
    ap.add_argument("--json", action="store_true", help="詳細 JSON を stdout")
    args = ap.parse_args()
    return run(args=args)


if __name__ == "__main__":
    raise SystemExit(main())
