#!/usr/bin/env python3
"""物件進行ゲート共有（114 振分 / 511 送信 / Slack Yes No）。

正本: docs/AIエージェントチーム/23_物件進行ゲート_Grok調査_20261012.md
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

REPO = Path(__file__).resolve().parents[1]
JST = ZoneInfo("Asia/Tokyo")
STATE_PATH = REPO / ".jarvis_state" / "property_gate.json"
DEALS_UI = "https://jarvis-trade-desk.vercel.app/realestate/deals"
DASHBOARD = (
    (os.environ.get("JARVIS_DASHBOARD_URL") or "").strip().rstrip("/")
    or "https://jarvis-dashboard-amber.vercel.app"
)
PYTHON_MAC = Path("/Users/matsunomasaharu2/selenium_env/venv/bin/python")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def now_jst_date() -> str:
    return datetime.now(JST).strftime("%Y-%m-%d")


def sb_client() -> Any:
    url = os.environ.get("JARVIS_SUPABASE_URL")
    key = os.environ.get("JARVIS_SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        raise SystemExit("JARVIS_SUPABASE_URL / JARVIS_SUPABASE_SERVICE_ROLE_KEY が必要です")
    from supabase import create_client

    return create_client(url, key)


def py() -> str:
    if PYTHON_MAC.is_file():
        return str(PYTHON_MAC)
    return sys.executable


def load_state() -> dict[str, Any]:
    if not STATE_PATH.is_file():
        return {"deals": {}, "digest_c_date": "", "disabled": False}
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"deals": {}, "digest_c_date": "", "disabled": False}


def save_state(st: dict[str, Any]) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(
        json.dumps(st, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def sj_of(deal: dict[str, Any]) -> dict[str, Any]:
    sj = deal.get("summary_json")
    return dict(sj) if isinstance(sj, dict) else {}


def grok_of(deal: dict[str, Any]) -> dict[str, Any]:
    sj = sj_of(deal)
    g = sj.get("grok") or sj.get("grok_result") or {}
    return dict(g) if isinstance(g, dict) else {}


def inquiry_status(deal: dict[str, Any]) -> str:
    col = str(deal.get("inquiry_status") or "").strip()
    sj = sj_of(deal)
    sj_st = str(sj.get("inquiry_status") or "").strip()
    # 列 CHECK 未適用時のフォールバック: sj の first_inquiry を優先
    if sj_st == "awaiting_first_inquiry" and (
        col in ("", "awaiting_grok") or bool(sj.get("awaiting_kurashift_first_inquiry"))
    ):
        return "awaiting_first_inquiry"
    return col or sj_st or "none"


def listen_value(deal: dict[str, Any]) -> str:
    g = grok_of(deal)
    for k in ("listen_value", "聞く", "listen"):
        v = g.get(k)
        if v:
            return str(v).strip()
    sj = sj_of(deal)
    for k in ("listen_value", "grok_listen"):
        v = sj.get(k)
        if v:
            return str(v).strip()
    return ""


def inquiry_action(deal: dict[str, Any]) -> str:
    sj = sj_of(deal)
    for k in ("s1_inquiry_action", "inquiry_action"):
        v = sj.get(k)
        if v:
            return str(v).strip()
    g = grok_of(deal)
    v = g.get("inquiry_action")
    return str(v).strip() if v else ""


def deal_url(deal_id: str) -> str:
    return f"{DEALS_UI}?deal={deal_id}"


def action_url(deal_id: str, action: str) -> str:
    """Slack Free 向け: リンククリックで Yes/No（token 付き）。"""
    token = (os.environ.get("PROPERTY_GATE_ACTION_TOKEN") or "").strip()
    base = f"{DASHBOARD}/api/slack/consult-action"
    q = f"deal_id={deal_id}&action={action}"
    if token:
        q += f"&token={token}"
    return f"{base}?{q}"


def post_slack(channel: str, text: str, *, dry_run: bool = False) -> dict[str, Any]:
    if dry_run:
        print(f"[dry-run] slack #{channel}:\n{text[:800]}")
        return {"ok": True, "dry_run": True}
    script = REPO / "scripts" / "jarvis_slack_webhook_post.py"
    if not script.is_file():
        return {"ok": False, "error": "webhook_post missing"}
    r = subprocess.run(
        [py(), str(script), "--channel", channel, "--text", text],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        env=os.environ.copy(),
        timeout=60,
    )
    out = ((r.stdout or "") + (r.stderr or "")).strip()
    return {"ok": r.returncode == 0, "code": r.returncode, "out": out}


def heal_handoff_status(sb: Any, deal: dict[str, Any]) -> dict[str, Any] | None:
    """旧 mislabel: kurashift_handoff → awaiting_grok を awaiting_first_inquiry へ。"""
    col = str(deal.get("inquiry_status") or "").strip()
    sj = sj_of(deal)
    action = inquiry_action(deal)
    flag = bool(sj.get("awaiting_kurashift_first_inquiry"))
    sj_st = str(sj.get("inquiry_status") or "").strip()
    needs = col == "awaiting_grok" and (
        action == "kurashift_handoff" or flag or sj_st == "awaiting_first_inquiry"
    )
    if not needs:
        return None
    sj["inquiry_status"] = "awaiting_first_inquiry"
    sj["awaiting_kurashift_first_inquiry"] = True
    sj["handoff_status_healed_at"] = now_iso()
    payload = {
        "inquiry_status": "awaiting_first_inquiry",
        "summary_json": sj,
        "updated_at": now_iso(),
    }
    try:
        sb.table("kurashift_re_deals").update(payload).eq("id", deal["id"]).execute()
    except Exception as e:
        print(f"# heal column fail deal={deal.get('id')}: {e}", file=sys.stderr)
        sb.table("kurashift_re_deals").update(
            {"summary_json": sj, "updated_at": now_iso()}
        ).eq("id", deal["id"]).execute()
        return None
    deal = {**deal, **payload}
    return deal


def classify_lane(deal: dict[str, Any]) -> dict[str, Any]:
    """A / B / C 振分。Web 再調査しない。"""
    from jarvis_kurashift_re_inquiry_rules import evaluate_inquiry_candidate

    listen = listen_value(deal)
    action = inquiry_action(deal)
    inq = inquiry_status(deal)
    sj = sj_of(deal)
    g = grok_of(deal)
    ev = evaluate_inquiry_candidate(deal)
    has_to = bool(ev.get("has_to"))
    score = 0.0
    try:
        score = float(deal.get("match_score") or 0)
    except (TypeError, ValueError):
        score = 0.0

    three = [
        f"土地値: {g.get('land100') or sj.get('land100') or '—'}",
        f"ハザード: {g.get('hazard_eval') or sj.get('hazard_eval') or '—'}",
        f"価格帯/スコア: {deal.get('price_man') or '—'}万 / score={score}",
    ]

    # C: 保留・見送り・investigate_only
    if action == "investigate_only" or listen in ("保留", "見送り", "見送り候補"):
        return {
            "lane": "C",
            "reason": f"listen={listen or '—'} action={action or '—'}",
            "listen": listen,
            "inquiry_action": action,
            "inquiry_status": inq,
            "has_to": has_to,
            "tier3": bool(ev.get("tier3")),
            "three_points": three,
            "eval": ev,
        }

    # A: portal_sent 済 / Tier3 / 聞く+portal
    portal_sent = action == "portal_sent" or inq == "awaiting_reply" and (
        sj.get("s1_inquiry_action") == "portal_sent"
        or sj.get("portal_sent") is True
    )
    if listen == "聞く" and (portal_sent or bool(ev.get("tier3"))):
        # Tier3 で To 無しは B へ落とす
        if bool(ev.get("tier3")) and not has_to and not portal_sent:
            return {
                "lane": "B",
                "reason": "tier3相当だが To 未解決",
                "listen": listen,
                "inquiry_action": action,
                "inquiry_status": inq,
                "has_to": has_to,
                "tier3": True,
                "three_points": three,
                "eval": ev,
            }
        return {
            "lane": "A",
            "reason": "portal_sent" if portal_sent else "tier3_auto",
            "listen": listen,
            "inquiry_action": action,
            "inquiry_status": inq,
            "has_to": has_to,
            "tier3": bool(ev.get("tier3")),
            "three_points": three,
            "eval": ev,
            "auto_send": not portal_sent and bool(ev.get("tier3")) and has_to,
        }

    # B: 聞く・送信待ち・境界
    if listen == "聞く" or inq == "awaiting_first_inquiry" or action == "kurashift_handoff":
        reason = "要人ゲート"
        if not has_to:
            reason = "To曖昧／未解決"
        elif inq == "awaiting_first_inquiry":
            reason = "第一問合せ待ち"
        return {
            "lane": "B",
            "reason": reason,
            "listen": listen,
            "inquiry_action": action,
            "inquiry_status": inq,
            "has_to": has_to,
            "tier3": bool(ev.get("tier3")),
            "three_points": three,
            "eval": ev,
        }

    return {
        "lane": "C",
        "reason": f"判定材料不足 listen={listen or '—'} inq={inq}",
        "listen": listen,
        "inquiry_action": action,
        "inquiry_status": inq,
        "has_to": has_to,
        "tier3": bool(ev.get("tier3")),
        "three_points": three,
        "eval": ev,
    }


def format_b_card(deal: dict[str, Any], lane: dict[str, Any]) -> str:
    deal_id = str(deal["id"])
    title = str(deal.get("title") or "物件")[:80]
    price = deal.get("price_man")
    price_s = f"{price}万" if price is not None else "—"
    pts = lane.get("three_points") or []
    lines = [
        "【物件進行ゲート】B 要判断",
        f"タイトル: {title}／{price_s}",
        f"deal_id: `{deal_id}`",
        f"判定: {lane.get('listen') or '—'}・score={deal.get('match_score')}・"
        f"inquiry_action={lane.get('inquiry_action') or '—'}",
        f"理由: {lane.get('reason')}",
        "見てほしい3点:",
        *[f"・{p}" for p in pts],
        f"詳細: {deal_url(deal_id)}",
        "",
        f"👉 Yes（問合せする）: {action_url(deal_id, 'yes')}",
        f"👉 No（見送り）: {action_url(deal_id, 'no')}",
        "",
        "（フォールバック）このスレに `Yes` / `No` と返信でも可。"
        " CLI: jarvis_property_gate_511.py --deal-id … --yes|--no",
    ]
    return "\n".join(lines)


def format_a_line(deal: dict[str, Any], lane: dict[str, Any]) -> str:
    return (
        f"【物件進行ゲート】A 自動 — {str(deal.get('title') or '')[:50]} "
        f"deal_id=`{deal['id']}` reason={lane.get('reason')}"
    )


def format_c_digest(items: list[tuple[dict[str, Any], dict[str, Any]]]) -> str:
    lines = [f"【物件進行ゲート】C 報告のみ（{now_jst_date()}・{len(items)}件）"]
    for deal, lane in items[:30]:
        lines.append(
            f"・{str(deal.get('title') or '')[:40]} "
            f"[{lane.get('listen') or '—'}] {lane.get('reason')}"
        )
    if len(items) > 30:
        lines.append(f"…他 {len(items) - 30} 件")
    return "\n".join(lines)


def already_gated(st: dict[str, Any], deal_id: str, lane: str) -> bool:
    d = (st.get("deals") or {}).get(deal_id) or {}
    if d.get("decision") in ("yes", "no", "sent", "skipped"):
        return True
    if lane == "B" and d.get("b_card_posted_at"):
        return True
    if lane == "A" and d.get("a_done_at"):
        return True
    return False


def mark_deal_state(st: dict[str, Any], deal_id: str, **fields: Any) -> None:
    deals = st.setdefault("deals", {})
    cur = dict(deals.get(deal_id) or {})
    cur.update(fields)
    cur["updated_at"] = now_iso()
    deals[deal_id] = cur


def fetch_gate_candidates(sb: Any, *, limit: int = 80) -> list[dict[str, Any]]:
    """Grok 由来・送信待ち近傍の deals。"""
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for status in ("awaiting_first_inquiry", "awaiting_grok", "none", "draft"):
        try:
            resp = (
                sb.table("kurashift_re_deals")
                .select("*")
                .eq("inquiry_status", status)
                .order("updated_at", desc=True)
                .limit(limit)
                .execute()
            )
        except Exception:
            continue
        for r in resp.data or []:
            rid = str(r.get("id") or "")
            if not rid or rid in seen:
                continue
            seen.add(rid)
            rows.append(r)
    # source mail_grok も拾う
    try:
        resp = (
            sb.table("kurashift_re_deals")
            .select("*")
            .eq("source", "mail_grok")
            .order("updated_at", desc=True)
            .limit(limit)
            .execute()
        )
        for r in resp.data or []:
            rid = str(r.get("id") or "")
            if rid and rid not in seen:
                seen.add(rid)
                rows.append(r)
    except Exception:
        pass
    return rows


def enqueue_inquiry_job(
    sb: Any,
    deal: dict[str, Any],
    *,
    source: str,
    dry_run: bool = False,
) -> dict[str, Any]:
    """既存 re_deal_inquiry_send ジョブを積む（Mac worker が送信）。"""
    deal_id = str(deal["id"])
    inq = inquiry_status(deal)
    if inq in ("sending", "awaiting_reply", "has_reply"):
        return {"ok": True, "skipped": "already_active", "inquiry_status": inq}

    # 二重ジョブ防止
    try:
        jobs = (
            sb.table("kurashift_jobs")
            .select("id, status, payload")
            .eq("job_type", "re_deal_inquiry_send")
            .in_("status", ["queued", "running", "succeeded"])
            .order("created_at", desc=True)
            .limit(40)
            .execute()
        )
        for j in jobs.data or []:
            p = j.get("payload") if isinstance(j.get("payload"), dict) else {}
            if p.get("deal_id") == deal_id or p.get("idempotency_key") == f"{deal_id}:first_inquiry":
                return {
                    "ok": True,
                    "skipped": "job_exists",
                    "job_id": j.get("id"),
                    "job_status": j.get("status"),
                }
    except Exception as e:
        return {"ok": False, "error": f"job_list: {e}"}

    now = now_iso()
    title = str(deal.get("title") or "")[:60]
    payload = {
        "deal_id": deal_id,
        "ui_confirmed": True,
        "ui_confirmed_at": now,
        "slack_gate_yes": True,
        "confirm_source": source,
        "idempotency_key": f"{deal_id}:first_inquiry",
    }
    if dry_run:
        return {"ok": True, "dry_run": True, "payload": payload}

    sj = sj_of(deal)
    sj["inquiry_status"] = "sending"
    sj["property_gate"] = {
        **(sj.get("property_gate") if isinstance(sj.get("property_gate"), dict) else {}),
        "decision": "yes",
        "at": now,
        "source": source,
    }
    try:
        sb.table("kurashift_re_deals").update(
            {
                "inquiry_status": "sending",
                "summary_json": sj,
                "updated_at": now,
            }
        ).eq("id", deal_id).execute()
    except Exception:
        sb.table("kurashift_re_deals").update(
            {"summary_json": sj, "updated_at": now}
        ).eq("id", deal_id).execute()

    ins = (
        sb.table("kurashift_jobs")
        .insert(
            {
                "job_type": "re_deal_inquiry_send",
                "title": f"第一問合せ(ゲート): {title}",
                "status": "queued",
                "payload": payload,
                "created_by": "property_gate",
            }
        )
        .select("id")
        .execute()
    )
    job_id = (ins.data or [{}])[0].get("id")
    return {"ok": True, "job_id": job_id, "inquiry_status": "sending"}


def mark_skip_no(sb: Any, deal: dict[str, Any], *, source: str) -> dict[str, Any]:
    deal_id = str(deal["id"])
    now = now_iso()
    sj = sj_of(deal)
    sj["inquiry_status"] = "none"
    sj["property_gate"] = {
        **(sj.get("property_gate") if isinstance(sj.get("property_gate"), dict) else {}),
        "decision": "no",
        "at": now,
        "source": source,
    }
    sj["auto_pass_reason"] = sj.get("auto_pass_reason") or "property_gate_no"
    try:
        sb.table("kurashift_re_deals").update(
            {
                "status": "passed",
                "inquiry_status": "none",
                "summary_json": sj,
                "updated_at": now,
            }
        ).eq("id", deal_id).execute()
    except Exception:
        sb.table("kurashift_re_deals").update(
            {"summary_json": sj, "updated_at": now}
        ).eq("id", deal_id).execute()
    return {"ok": True, "decision": "no", "deal_id": deal_id}
