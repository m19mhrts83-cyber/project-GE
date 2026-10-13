#!/usr/bin/env python3
"""物件進行ゲート共有（114 振分 / 511 送信 / Slack Yes No）。

正本: docs/AIエージェントチーム/23_物件進行ゲート_Grok調査_20261012.md
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

try:
    import fcntl
except ImportError:  # pragma: no cover
    fcntl = None  # type: ignore

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
        return {"deals": {}, "by_fp": {}, "digest_c_date": "", "disabled": False}
    try:
        st = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        if not isinstance(st.get("deals"), dict):
            st["deals"] = {}
        if not isinstance(st.get("by_fp"), dict):
            st["by_fp"] = {}
        return st
    except Exception:
        return {"deals": {}, "by_fp": {}, "digest_c_date": "", "disabled": False}


def save_state(st: dict[str, Any]) -> None:
    """並列 114 実行でも潰さないよう排他付きで保存。"""
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(st, ensure_ascii=False, indent=2) + "\n"
    if fcntl is None:
        STATE_PATH.write_text(payload, encoding="utf-8")
        return
    lock_path = STATE_PATH.with_suffix(".json.lock")
    with open(lock_path, "a+", encoding="utf-8") as lf:
        fcntl.flock(lf.fileno(), fcntl.LOCK_EX)
        try:
            # 他プロセスが先に書いた内容をマージ（deals / by_fp）
            cur = load_state()
            deals = dict(cur.get("deals") or {})
            deals.update(st.get("deals") or {})
            by_fp = dict(cur.get("by_fp") or {})
            by_fp.update(st.get("by_fp") or {})
            merged = {
                **cur,
                **{k: v for k, v in st.items() if k not in ("deals", "by_fp")},
                "deals": deals,
                "by_fp": by_fp,
            }
            STATE_PATH.write_text(
                json.dumps(merged, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            st.clear()
            st.update(merged)
        finally:
            fcntl.flock(lf.fileno(), fcntl.LOCK_UN)


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
    """詳細は短縮リダイレクト（長い trade-desk URL を Slack に出さない）。"""
    return f"{DASHBOARD}/api/g/d/{deal_id}"


def action_sig(deal_id: str, action: str) -> str:
    token = (os.environ.get("PROPERTY_GATE_ACTION_TOKEN") or "").strip()
    act = "yes" if str(action).lower() in ("yes", "y") else "no"
    return hmac.new(
        token.encode("utf-8"),
        f"{deal_id}:{act}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()[:10]


def action_url(deal_id: str, action: str) -> str:
    """Slack Free 向け短縮リンク（HMAC。フル token を URL に載せない）。"""
    act = "yes" if str(action).lower() in ("yes", "y") else "no"
    kind = "y" if act == "yes" else "n"
    sig = action_sig(deal_id, act)
    return f"{DASHBOARD}/api/g/{kind}/{deal_id}?s={sig}"


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

    land_disp = (
        g.get("land100_ratio")
        or g.get("land100")
        or sj.get("land100_ratio")
        or sj.get("land100")
        or "—"
    )
    haz_disp = g.get("hazard_eval") or sj.get("hazard_eval") or "—"
    three = [
        f"土地値: {land_disp}",
        f"ハザード: {haz_disp}",
        f"価格帯/スコア: {deal.get('price_man') or g.get('price_man') or '—'}万 / score={score}",
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


def _clean_listing_url(raw: str) -> str:
    s = str(raw or "").strip()
    if not s:
        return ""
    # 「URL （注釈）」形式を落とす
    s = s.split("（")[0].split("(")[0].strip()
    try:
        from urllib.parse import parse_qs, urlparse

        u = urlparse(s)
        if u.hostname in ("www.google.com", "google.com") and u.path == "/url":
            q = (parse_qs(u.query).get("q") or [None])[0]
            if q:
                return str(q).strip()
    except Exception:
        pass
    return s


def judgment_rows(
    deal: dict[str, Any], *, max_cell: int = 120
) -> list[tuple[str, str]]:
    """Slack／詳細ページ共通の判断材料行（項目, 値）。"""
    g = grok_of(deal)
    sj = sj_of(deal)

    def pick(*keys: str, default: str = "—") -> str:
        for k in keys:
            v = g.get(k)
            if v is None or v == "":
                v = sj.get(k)
            if v is None or v == "":
                continue
            s = str(v).strip()
            if s:
                return s
        return default

    price = deal.get("price_man")
    if price is None:
        price = g.get("price_man")
    try:
        price_s = f"{int(round(float(price)))}万" if price is not None else "—"
    except (TypeError, ValueError):
        price_s = f"{price}万" if price is not None else "—"

    url = _clean_listing_url(pick("url", "listing_url", "inquiry_url", default=""))
    loc = pick("location")
    if loc == "—":
        loc = str(deal.get("area") or "—")
    lv = pick("listen_value")
    if lv == "—":
        lv = listen_value(deal) or "—"
    ia = pick("inquiry_action")
    if ia == "—":
        ia = inquiry_action(deal) or "—"
    rows: list[tuple[str, str]] = [
        ("所在", loc),
        ("価格", price_s),
        ("土地", pick("land_area")),
        ("土地値倍率", pick("land100_ratio", "land100", "land_ratio")),
        ("土地評価(万)", pick("land_appraisal_man")),
        ("路線価手法", pick("land_method")),
        ("建物", pick("building")),
        ("ハザード総合", pick("hazard_eval")),
        ("洪水", pick("hazard_flood")),
        ("高潮", pick("hazard_storm_surge")),
        ("急傾斜", pick("hazard_landslide")),
        ("内水", pick("hazard_inland")),
        ("聞く/保留", lv),
        ("問合せ経路", ia),
        ("score", str(deal.get("match_score") if deal.get("match_score") is not None else "—")),
    ]
    if url:
        rows.append(("掲載URL", url))

    out: list[tuple[str, str]] = []
    for label, val in rows:
        v = val.replace("\n", " ").strip() or "—"
        if max_cell and len(v) > max_cell:
            v = v[: max_cell - 1] + "…"
        out.append((label, v))
    return out


_NUM = re.compile(r"-?\d[\d,]*(?:\.\d+)?")
_SCEN = re.compile(r"([\d,]+(?:\.\d+)?)\s*[（(]\s*([^）)]*)\s*[）)]")


def _first_number(raw: Any) -> float | None:
    m = _NUM.search(str(raw or ""))
    if not m:
        return None
    try:
        return float(m.group(0).replace(",", ""))
    except ValueError:
        return None


def _area_m2(raw: Any) -> float | None:
    """面積文字列を㎡へ。㎡表記優先、無ければ坪を㎡換算。"""
    s = str(raw or "")
    m = re.search(r"([\d,]+(?:\.\d+)?)\s*(?:㎡|m2|平米|m²)", s)
    if m:
        return float(m.group(1).replace(",", ""))
    m = re.search(r"([\d,]+(?:\.\d+)?)\s*坪", s)
    if m:
        return float(m.group(1).replace(",", "")) * 3.30578
    return _first_number(s)


def _scenarios(raw: Any) -> list[tuple[float, str]]:
    """「参考1,494（91E）／1,805（110E）」→ [(1494.0,'91E'), (1805.0,'110E')]。"""
    s = str(raw or "")
    out: list[tuple[float, str]] = []
    for num, tag in _SCEN.findall(s):
        try:
            out.append((float(num.replace(",", "")), tag.strip()))
        except ValueError:
            continue
    if not out:
        n = _first_number(s)
        if n is not None:
            out.append((n, ""))
    return out


def land_value_lines(deal: dict[str, Any]) -> list[str]:
    """概要用: 土地値（相続税路線価×面積）と土地値率（＝土地値÷価格）。"""
    g = grok_of(deal)
    sj = sj_of(deal)

    def pick(*keys: str) -> str:
        for k in keys:
            v = g.get(k)
            if v in (None, ""):
                v = sj.get(k)
            if v not in (None, ""):
                return str(v).strip()
        return ""

    price = _first_number(
        deal.get("price_man")
        if deal.get("price_man") is not None
        else pick("price_man")
    )
    vals = _scenarios(pick("land_appraisal_man"))
    if not vals:  # 相続税路線価(万円/坪) × 面積(㎡) から算出
        rp = _first_number(pick("route_price_tsubo"))
        area = _area_m2(pick("land_area"))
        if rp and area:
            vals = [(rp * area / 3.30578, "")]
    ratios = _scenarios(pick("land100_ratio", "land_ratio", "land100"))
    if not vals and ratios and price:  # 率しか無い時は価格×率で金額を逆算
        vals = [
            (price * (n / 100) if n >= 10 else price * n, t) for n, t in ratios
        ]

    value_s = "／".join(
        f"約{v:,.0f}万" + (f"（{t}）" if t else "") for v, t in vals
    )
    if price and vals:
        ratio_s = "／".join(f"{v / price * 100:.0f}%" for v, _ in vals)
    elif ratios:
        ratio_s = "／".join(
            f"{n * 100:.0f}%" if n < 10 else f"{n:.0f}%" for n, _ in ratios
        )
    else:
        ratio_s = ""

    out: list[str] = []
    if value_s:
        out.append(f"• 土地値：{value_s}")
    if ratio_s:
        out.append(f"• 土地値率：{ratio_s}（＝土地値÷価格）")
    return out


def format_judgment_card(
    deal: dict[str, Any], rows: list[tuple[str, str]]
) -> list[str]:
    """モバイル優先の判断材料カード（等幅表を使わず、iPhone で折返しても崩れない）。"""
    d: dict[str, str] = {}
    for label, val in rows:
        d[label] = (val or "").replace("\n", " ").strip() or "—"

    summary = ["*■ 概要*"]
    if "価格" in d:
        summary.append(f"• 価格：{d['価格']}")
    summary += land_value_lines(deal)
    if "所在" in d:
        summary.append(f"• 所在：{d['所在']}")

    prop = ["*■ 物件*"]
    for label in ("土地", "路線価手法", "建物"):
        if label in d:
            prop.append(f"• {label}：{d[label]}")

    risk = ["*■ リスク（足切り）*"]
    if "ハザード総合" in d:
        risk.append(f"• ハザード総合：{d['ハザード総合']}")
    indiv = [f"{k}={d[k]}" for k in ("洪水", "高潮", "急傾斜", "内水") if k in d]
    if indiv:
        risk.append("• 個別：" + "・".join(indiv))

    tail = ["*■ 判定材料*"]
    tail += [f"• {k}：{d[k]}" for k in ("聞く/保留", "問合せ経路", "score") if k in d]
    if d.get("掲載URL"):
        tail.append(f"• 掲載URL：{d['掲載URL']}")

    sections = [summary, prop, risk] + ([tail] if len(tail) > 1 else [])
    lines: list[str] = []
    for i, sec in enumerate(sections):
        if i:
            lines.append("")
        lines += sec
    return lines


def format_b_card(deal: dict[str, Any], lane: dict[str, Any]) -> str:
    deal_id = str(deal["id"])
    title = str(deal.get("title") or "物件")[:80]
    rows = judgment_rows(deal, max_cell=160)
    lines = [
        "【物件進行ゲート】B 要判断",
        f"*{title}*",
        f"理由：{lane.get('reason')} ・ listen={lane.get('listen') or '—'}",
        "",
        *format_judgment_card(deal, rows),
        "",
        "*■ 判断（Yes＝この内容で第一問合せを了承）*",
        f"✅ <{action_url(deal_id, 'yes')}|問合せする（Yes）>",
        f"🚫 <{action_url(deal_id, 'no')}|見送り（No）>",
        f"🔎 <{deal_url(deal_id)}|全文を見る（ログイン不要）>",
        "",
        "（このスレに `Yes` / `No` と返信でもOK）",
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


def deal_fp_key(deal: dict[str, Any]) -> str:
    try:
        from jarvis_kurashift_re_deal_dedupe_merge import deal_fingerprint

        return deal_fingerprint(deal) or ""
    except Exception:
        return str(deal.get("property_fingerprint") or "")


def already_gated(
    st: dict[str, Any],
    deal_id: str,
    lane: str,
    *,
    deal: dict[str, Any] | None = None,
) -> bool:
    d = (st.get("deals") or {}).get(deal_id) or {}
    if d.get("decision") in ("yes", "no", "sent", "skipped"):
        return True
    if lane == "B" and d.get("b_card_posted_at"):
        return True
    if lane == "A" and d.get("a_done_at"):
        return True
    # 同一 fingerprint の別 deal が既に B 投稿済みなら再掲しない
    if lane == "B" and deal is not None:
        fp = deal_fp_key(deal)
        if fp:
            prev = (st.get("by_fp") or {}).get(fp) or {}
            if prev.get("b_card_posted_at") or prev.get("decision") in (
                "yes",
                "no",
                "sent",
            ):
                return True
        sj = sj_of(deal)
        gate = sj.get("property_gate") if isinstance(sj.get("property_gate"), dict) else {}
        if gate.get("decision") in ("yes", "no", "sent"):
            return True
        if sj.get("inquiry_sent_at") or inquiry_status(deal) in (
            "awaiting_reply",
            "has_reply",
            "sending",
        ):
            return True
    return False


def mark_deal_state(
    st: dict[str, Any],
    deal_id: str,
    *,
    deal: dict[str, Any] | None = None,
    **fields: Any,
) -> None:
    deals = st.setdefault("deals", {})
    cur = dict(deals.get(deal_id) or {})
    cur.update(fields)
    cur["updated_at"] = now_iso()
    if deal is not None:
        fp = deal_fp_key(deal)
        if fp:
            cur["fingerprint"] = fp
            by_fp = st.setdefault("by_fp", {})
            fp_cur = dict(by_fp.get(fp) or {})
            fp_cur.update(fields)
            fp_cur["deal_id"] = deal_id
            fp_cur["updated_at"] = cur["updated_at"]
            by_fp[fp] = fp_cur
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
