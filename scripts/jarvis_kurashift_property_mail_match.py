#!/usr/bin/env python3
"""物件紹介メール → kurashift_re_deals 候補（送信なし・dry-run 既定）。

使用アカウント: admin（主） + estate（補完） / Gmail API

振り分け（二重経路可）:
  - 物件紹介・購入シグナル → 本スクリプト（KURASHIFT 評価）。**パートナー差出も含む**
  - パートナー差出は Jarvis「パートナー」レーンにも残る（管理軸）。排他ではない
  - その他の要確認／要約 → Jarvis ダッシュボード general

  cd ~/git-repos && set -a && source .env.jarvis_private && set +a
  ~/selenium_env/venv/bin/python scripts/jarvis_kurashift_property_mail_match.py --dry-run
  ~/selenium_env/venv/bin/python scripts/jarvis_kurashift_property_mail_match.py --apply
  # 千三つ「確認した／対象外」後の既読
  ~/selenium_env/venv/bin/python scripts/jarvis_kurashift_property_mail_match.py \\
    --mark-read-deal-id <uuid>

取込時: 明らかに対象外（ノイズ件名・低スコア・区分/都内寄り等）は
status=passed で残し、その場で Gmail 既読にする。境界候補は未読のまま。
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import re
import sys
from datetime import datetime, timezone
from email.utils import parseaddr, parsedate_to_datetime
from pathlib import Path
from typing import Any

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

REPO = Path(__file__).resolve().parents[1]
MANUAL = REPO / "215_kamiooya" / "C1_cursor" / "1b_Cursorマニュアル"
SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/gmail.send",
]

# パートナー判定用（メタ付与。取込除外には使わない）
CONTACT_YAML = (
    Path.home()
    / "Library/CloudStorage/OneDrive-個人用/215_神・大家さん倶楽部"
    / "C2_ルーティン作業/26_パートナー社への相談/000_共通/連絡先一覧.yaml"
)
CONTACT_CI = (
    REPO
    / "215_kamiooya/C1_cursor/1b_Cursorマニュアル/連絡先一覧.snapshot.yaml"
)

# 広めに拾い、criteria でスコア
GMAIL_QUERY = (
    "(物件 OR 戸建 OR 戸建て OR 収益物件 OR 利回り OR 土地値 OR 不動産投資 OR 紹介)"
    " newer_than:{days}d -unsubscribe"
)

# 候補として残す最低点（未満は取込時に対象外＋既読）
CANDIDATE_SCORE_MIN = 2.0
# 戸建+エリア程度で内見（詳細取り寄せ〜日程調整）へ
VIEWING_SCORE_MIN = 5.0

SUBJECT_NOISE = (
    "号外",
    "ダイジェスト",
    "税理士",
    "平均年収",
    "夕方メール",
    "ワンルーム投資やめとけ",
    "成果報告",
)

CITY_HINTS = [
    "岡崎",
    "碧南",
    "知多",
    "安城",
    "豊田",
    "瀬戸",
    "春日井",
    "犬山",
    "一宮",
    "各務原",
    "岐阜",
    "大垣",
    "桑名",
    "四日市",
    "津市",
    "鈴鹿",
    "愛知",
    "岐阜県",
    "三重",
    "名古屋",
]

TOKEN_BY_SOURCE = {
    "mail_admin": "token_livingsupport.json",
    "mail_estate": "token_estate.json",
    "mail_grok": "token_estate.json",
}

GROK_QUERY = 'subject:"[Grok調査]" newer_than:{days}d'
GROK_SUBJECT_PREFIX = "[Grok調査]"


def _field_after_label(text: str, label: str) -> str:
    """Markdown 行 `- ラベル: 値` から値を取る。"""
    pat = rf"^\s*[-*]\s*{re.escape(label)}\s*[:：]\s*(.+)$"
    for line in text.splitlines():
        m = re.match(pat, line.strip())
        if m:
            return m.group(1).strip()
    return ""


def _section_text(text: str, heading_prefix: str) -> str:
    """## 見出し以降〜次の ## まで。"""
    lines = text.splitlines()
    buf: list[str] = []
    in_sec = False
    for line in lines:
        if re.match(rf"^##\s*{re.escape(heading_prefix)}", line.strip()):
            in_sec = True
            continue
        if in_sec and re.match(r"^##\s", line.strip()):
            break
        if in_sec:
            buf.append(line)
    return "\n".join(buf)


def _field_in_section(text: str, section_prefix: str, label: str) -> str:
    return _field_after_label(_section_text(text, section_prefix), label)


def parse_grok_report(text: str) -> dict[str, Any]:
    """Grok 調査レポート（Phase 2a+ 形式）を summary_json.grok に展開。"""
    out: dict[str, Any] = {"source_tag": "grok_bot"}
    loc = _field_after_label(text, "所在")
    if loc:
        out["location"] = loc
    price_raw = _field_after_label(text, "価格_万")
    if price_raw:
        out["price_man_raw"] = price_raw
        pm = re.search(r"(\d+(?:\.\d+)?)", price_raw.replace(",", ""))
        if pm:
            try:
                out["price_man"] = float(pm.group(1))
            except Exception:
                pass
    for key, label in (
        ("land_area", "土地面積"),
        ("building", "建物"),
        ("parking", "駐車場"),
        ("url", "URL"),
    ):
        val = _field_in_section(text, "物件", label) or _field_after_label(text, label)
        if val:
            out[key] = val
    # 土地評価（## 土地評価 セクション）
    land_sec = _section_text(text, "土地評価")
    for key, label in (
        ("land_method", "方式"),
        ("route_price_tsubo", "路線価_万円_坪"),
        ("land_ratio", "倍率"),
        ("land_appraisal_man", "土地積算_万円"),
        ("land100_ratio", "土地値100%_比率"),
        ("land100", "土地値100%判定"),
        ("land_basis_url", "根拠URL"),
    ):
        val = _field_after_label(land_sec, label) if land_sec else _field_after_label(text, label)
        if val:
            out[key] = val
    # ハザード（## ハザード セクション）
    haz_sec = _section_text(text, "ハザード")
    for key, label in (
        ("hazard_survey_url", "調査URL"),
        ("hazard_flood", "洪水"),
        ("hazard_landslide", "土砂"),
        ("hazard_storm_surge", "高潮"),
        ("hazard_inland", "内水"),
        ("hazard_eval", "評価"),
        ("hazard_basis_url", "根拠URL"),
    ):
        val = _field_after_label(haz_sec, label) if haz_sec else ""
        if val:
            out[key] = val
    out["population_eval"] = _field_in_section(text, "人口", "評価") or _field_after_label(
        text, "評価"
    )
    pop_summary = _field_in_section(text, "人口", "表")
    pop_table = ""
    for line in _section_text(text, "人口").splitlines():
        if line.strip().startswith("|"):
            pop_table = (pop_table + "\n" + line).strip()
    if pop_table:
        out["population_table"] = pop_table[:800]
    elif pop_summary:
        out["population_table"] = pop_summary[:800]
    out["listen_value"] = _field_in_section(text, "総合", "聞く価値") or _field_after_label(
        text, "聞く価値"
    )
    out["reason_line"] = _field_in_section(text, "総合", "理由1行") or _field_after_label(
        text, "理由1行"
    )
    # ## 問合せ（S1 portal / KURASHIFT handoff · 2026-08-25）
    inq_sec = _section_text(text, "問合せ")
    for key, label in (
        ("inquiry_action", "inquiry_action"),
        ("agent_email_available", "agent_email_available"),
        ("inquiry_url", "inquiry_url"),
        ("portal", "portal"),
        ("inquiry_sent_at_note", "sent_at"),
        ("inquiry_note", "note"),
    ):
        val = (
            _field_after_label(inq_sec, label)
            if inq_sec
            else _field_after_label(text, label)
        )
        if val:
            out[key] = val.strip()
    # bare key: value lines (YAML-ish)
    if not out.get("inquiry_action"):
        m = re.search(
            r"inquiry_action\s*[:：]\s*(portal_sent|kurashift_handoff|investigate_only)",
            text,
            re.I,
        )
        if m:
            out["inquiry_action"] = m.group(1).lower()
    rid = _field_after_label(text, "report_id")
    if not rid:
        m = re.search(r"report_id:\s*(\S+)", text)
        if m:
            rid = m.group(1)
    if rid:
        out["report_id"] = rid
    return out


def apply_s1_inquiry_fields(
    sb: Any,
    *,
    deal_id: str,
    grok: dict[str, Any],
    gmail_id: str | None = None,
) -> dict[str, Any]:
    """[Grok調査] の inquiry_action を deals.inquiry_* と events に反映。"""
    action = str(grok.get("inquiry_action") or "").strip().lower()
    if not action:
        return {"ok": False, "skipped": "no_inquiry_action"}
    now = datetime.now(timezone.utc).isoformat()
    result: dict[str, Any] = {"ok": True, "action": action, "deal_id": deal_id}

    try:
        from jarvis_kurashift_deal_events import insert_deal_event
        from jarvis_kurashift_re_inquiry import get_deal, update_inquiry
    except Exception as e:
        return {"ok": False, "error": f"import: {e}"}

    deal = get_deal(sb, deal_id)
    if not deal:
        return {"ok": False, "error": "deal not found"}

    if action == "portal_sent":
        update_inquiry(
            sb,
            deal,
            inquiry_status="awaiting_reply",
            inquiry_sent_at=now,
            summary_json={
                "inquiry_channel": "s1_portal",
                "inquiry_url": grok.get("inquiry_url"),
                "portal": grok.get("portal"),
                "s1_inquiry_note": grok.get("inquiry_note"),
                "s1_gmail_id": gmail_id,
            },
        )
        insert_deal_event(
            sb,
            deal_id=deal_id,
            event_type="inquiry_sent",
            summary=f"S1 ポータル問合せ: {(grok.get('inquiry_url') or '')[:80]}",
            actor="s1_portal",
            to_status="awaiting_reply",
            payload={
                "inquiry_action": action,
                "portal": grok.get("portal"),
                "inquiry_url": grok.get("inquiry_url"),
                "gmail_id": gmail_id,
            },
        )
        result["inquiry_status"] = "awaiting_reply"
    elif action == "kurashift_handoff":
        update_inquiry(
            sb,
            deal,
            inquiry_status="awaiting_grok",
            summary_json={
                "inquiry_channel": "grok_handoff",
                "inquiry_url": grok.get("inquiry_url"),
                "portal": grok.get("portal"),
                "s1_inquiry_note": grok.get("inquiry_note"),
                "s1_gmail_id": gmail_id,
                "awaiting_kurashift_first_inquiry": True,
            },
        )
        insert_deal_event(
            sb,
            deal_id=deal_id,
            event_type="grok_handoff_ready",
            summary="S1: 仲介メール可 → KURASHIFT第一問合せ待ち",
            actor="s1",
            to_status="awaiting_grok",
            payload={"inquiry_action": action, "gmail_id": gmail_id},
        )
        result["inquiry_status"] = "awaiting_grok"
    elif action == "investigate_only":
        insert_deal_event(
            sb,
            deal_id=deal_id,
            event_type="grok_applied",
            summary="S1 調査のみ（問合せなし）",
            actor="s1",
            payload={"inquiry_action": action, "gmail_id": gmail_id},
        )
        result["inquiry_status"] = "none"
    else:
        return {"ok": False, "skipped": f"unknown_action:{action}"}
    return result


def grok_match_score(grok: dict[str, Any], base_score: float) -> float:
    score = base_score
    listen = str(grok.get("listen_value") or "")
    land100 = str(grok.get("land100") or "")
    hazard = str(grok.get("hazard_eval") or "")
    if listen == "聞く":
        score += 4.0
    elif listen == "保留":
        score += 1.5
    elif listen == "見送り":
        score -= 2.0
    if land100 == "聞く":
        score += 2.0
    elif land100 == "見送り":
        score -= 1.5
    if grok.get("land_method") == "路線価" and grok.get("route_price_tsubo"):
        score += 0.5
    if grok.get("parking") == "あり":
        score += 0.5
    if hazard == "除外":
        score -= 4.0
    elif hazard == "注意":
        score -= 1.0
    elif hazard == "OK":
        score += 0.5
    for k in ("hazard_flood", "hazard_landslide", "hazard_storm_surge", "hazard_inland"):
        if str(grok.get(k) or "") == "該当":
            score -= 1.5
            break
    return round(score, 2)


def sb_client() -> Any:
    url = os.environ.get("JARVIS_SUPABASE_URL")
    key = os.environ.get("JARVIS_SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        raise SystemExit("JARVIS_SUPABASE_URL / JARVIS_SUPABASE_SERVICE_ROLE_KEY が必要です")
    from supabase import create_client

    return create_client(url, key)


def gmail_service(token_name: str):
    path = MANUAL / token_name
    if not path.is_file():
        raise FileNotFoundError(path)
    creds = Credentials.from_authorized_user_file(str(path), SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
    return build("gmail", "v1", credentials=creds, cache_discovery=False)


def _partner_filters() -> tuple[set[str], set[str]]:
    sys.path.insert(0, str(REPO / "scripts"))
    from jarvis_night_triage_general import (  # type: ignore
        load_partner_filters,
        resolve_contact_yaml,
    )

    path = CONTACT_YAML if CONTACT_YAML.is_file() else CONTACT_CI
    return load_partner_filters(resolve_contact_yaml(path if path.is_file() else None))


def _partner_name_by_email() -> dict[str, str]:
    """email_lower → partner name（YAML）。"""
    import yaml

    path = CONTACT_YAML if CONTACT_YAML.is_file() else CONTACT_CI
    if not path.is_file():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    out: dict[str, str] = {}
    for p in data.get("partners") or []:
        if not isinstance(p, dict):
            continue
        name = str(p.get("name") or p.get("folder") or "").strip()
        if not name:
            continue
        for e in p.get("emails") or []:
            if isinstance(e, str) and "@" in e:
                out[e.strip().lower()] = name
    return out


def _partner_meta(
    hm: dict[str, str],
    emails: set[str],
    domains: set[str],
    name_by_email: dict[str, str],
) -> dict[str, Any]:
    sys.path.insert(0, str(REPO / "scripts"))
    from jarvis_night_triage_general import is_partner_address  # type: ignore

    _, addr = parseaddr(hm.get("from") or "")
    addr = (addr or "").strip().lower()
    if not is_partner_address(addr, emails, domains):
        return {"is_partner": False}
    name = name_by_email.get(addr) or ""
    if not name and "@" in addr:
        dom = addr.split("@", 1)[1]
        for e, n in name_by_email.items():
            if e.endswith("@" + dom):
                name = n
                break
    return {"is_partner": True, "partner_name": name or addr}


def decode_body(payload: dict) -> str:
    parts = [payload]
    texts: list[str] = []
    while parts:
        p = parts.pop()
        body = p.get("body") or {}
        data = body.get("data")
        mime = (p.get("mimeType") or "").lower()
        if data and ("text/plain" in mime or not p.get("parts")):
            try:
                texts.append(base64.urlsafe_b64decode(data).decode("utf-8", "replace"))
            except Exception:
                pass
        for ch in p.get("parts") or []:
            parts.append(ch)
    return "\n".join(texts)[:8000]


def header_map(headers: list[dict]) -> dict[str, str]:
    out: dict[str, str] = {}
    for h in headers or []:
        out[(h.get("name") or "").lower()] = h.get("value") or ""
    return out


def score_text(text: str, criteria_blob: str) -> tuple[float, list[str]]:
    hits: list[str] = []
    score = 0.0
    for city in CITY_HINTS:
        if city in text:
            hits.append(city)
            score += 2.0 if city in criteria_blob or city in ("愛知", "岐阜", "三重") else 1.0
    if re.search(r"戸建|戸建て", text):
        hits.append("戸建")
        score += 3.0
    if re.search(r"土地値", text):
        hits.append("土地値")
        score += 2.0
    if re.search(r"利回り\s*[１２3-9０-９\d]", text) or "利回り" in text:
        hits.append("利回り")
        score += 1.5
    # 価格帯（戸建想定 500〜3500万）
    pm = re.search(r"(\d{2,5})\s*万", text)
    if pm:
        try:
            man = float(pm.group(1))
            if 500 <= man <= 3500:
                hits.append(f"価格帯{int(man)}")
                score += 1.5
            elif man > 8000:
                score -= 1.5
        except Exception:
            pass
    if "万円" in text or pm:
        score += 0.5
    # 区分・都内寄りは減点（東海戸建方針）
    if re.search(r"区分|ワンルーム|都内|東京２３|東京23", text) and not re.search(
        r"戸建|戸建て", text
    ):
        hits.append("区分/都内-")
        score -= 2.0
    if re.search(r"アパート|マンション一棟", text) and not re.search(r"戸建|戸建て", text):
        score -= 0.5
    if re.search(r"RC|鉄骨", text) and not re.search(r"戸建|戸建て", text):
        hits.append("RC")
        score += 0.5
    if "海沿" in text and "除外" not in criteria_blob:
        score -= 0.5
    return score, hits


def clearly_out_of_scope(subject: str, text: str, score: float) -> tuple[bool, str]:
    """取込時点で明らかに対象外か（境界候補は False）。"""
    if any(n in subject for n in SUBJECT_NOISE):
        return True, "subject_noise"
    has_kodate = bool(re.search(r"戸建|戸建て", text))
    if re.search(r"区分|ワンルーム", text) and not has_kodate:
        return True, "mansion_unit"
    if re.search(r"都内|東京２３|東京23|東京23区", text) and not has_kodate:
        tokai = any(c in text for c in CITY_HINTS)
        if not tokai:
            return True, "tokyo_focus"
    if score < CANDIDATE_SCORE_MIN:
        try:
            from jarvis_kurashift_re_inquiry_rules import should_skip_low_score_auto_pass

            if should_skip_low_score_auto_pass(
                text, score, city_hints=CITY_HINTS, min_score=CANDIDATE_SCORE_MIN
            ):
                return False, ""
        except Exception:
            pass
        return True, "low_score"
    return False, ""


def load_criteria_blob(sb: Any) -> str:
    ver = (
        sb.table("kurashift_buy_plan_versions")
        .select("id")
        .eq("is_canonical", True)
        .limit(1)
        .execute()
    )
    vid = (ver.data or [{}])[0].get("id")
    if not vid:
        return ""
    rows = (
        sb.table("kurashift_buy_plan_criteria")
        .select("raw_text")
        .eq("version_id", vid)
        .execute()
    )
    return "\n".join((r.get("raw_text") or "") for r in (rows.data or []))


def _deal_row_from_message(
    *,
    gmail_id: str,
    source: str,
    subject: str,
    text: str,
    hm: dict[str, str],
    sc: float,
    hits: list[str],
    status: str,
    auto_pass_reason: str | None = None,
    partner_meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    date_hdr = hm.get("date")
    try:
        occurred = parsedate_to_datetime(date_hdr) if date_hdr else datetime.now(timezone.utc)
        if occurred.tzinfo is None:
            occurred = occurred.replace(tzinfo=timezone.utc)
    except Exception:
        occurred = datetime.now(timezone.utc)
    area = next(
        (c for c in CITY_HINTS if c in text and c not in ("愛知", "岐阜県", "三重")),
        None,
    )
    price = None
    pm = re.search(r"(\d{2,5})\s*万", text)
    if pm:
        try:
            price = float(pm.group(1))
        except Exception:
            pass
    yld = None
    ym = re.search(r"利回り\s*[：:]?\s*(\d+(?:\.\d+)?)\s*%", text)
    if ym:
        yld = float(ym.group(1)) / 100.0
    sj: dict[str, Any] = {
        "gmail_id": gmail_id,
        "from": hm.get("from", "")[:200],
        "hits": hits,
        "snippet": text[:500],
        "account": source,
    }
    reply_to_raw = hm.get("reply-to") or hm.get("reply_to") or ""
    if reply_to_raw:
        sj["reply_to"] = str(reply_to_raw)[:200]
    if partner_meta:
        sj["is_partner"] = bool(partner_meta.get("is_partner"))
        if partner_meta.get("partner_name"):
            sj["partner_name"] = partner_meta["partner_name"]
    if auto_pass_reason:
        sj["auto_pass_reason"] = auto_pass_reason
        sj["auto_pass_at_ingest"] = True
    try:
        from email.utils import parseaddr

        from jarvis_kurashift_vendor_match import match_vendor

        _, from_email = parseaddr(hm.get("from", ""))
        hit = match_vendor(
            from_email or "",
            from_display=hm.get("from", ""),
            subject=subject,
        )
        if hit and hit.get("id"):
            sj["vendor_id"] = hit["id"]
            sj["vendor_name"] = hit.get("name")
    except Exception:
        pass
    return {
        "title": subject[:180],
        "status": status,
        "source": source,
        "area": area,
        "structure": "戸建" if re.search(r"戸建|戸建て", text) else None,
        "price_man": price,
        "yield_pct": yld,
        "match_score": round(sc, 2),
        "summary_json": sj,
        "advice_json": {},
        "first_seen_at": occurred.isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


def fetch_account(
    token_name: str,
    source: str,
    *,
    days: int,
    limit: int,
    criteria_blob: str,
    partner_emails: set[str] | None = None,
    partner_domains: set[str] | None = None,
    partner_names: dict[str, str] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Returns (candidates_to_review, auto_pass_out_of_scope).

    パートナー差出も評価土俵に載せる（Jarvis partner レーンと併存）。
    """
    if partner_emails is None or partner_domains is None:
        partner_emails, partner_domains = _partner_filters()
    if partner_names is None:
        partner_names = _partner_name_by_email()
    svc = gmail_service(token_name)
    q = GMAIL_QUERY.format(days=days)
    resp = (
        svc.users()
        .messages()
        .list(userId="me", q=q, maxResults=min(limit, 50))
        .execute()
    )
    keepers: list[dict[str, Any]] = []
    auto_pass: list[dict[str, Any]] = []
    partner_hits = 0
    for m in resp.get("messages") or []:
        full = (
            svc.users()
            .messages()
            .get(userId="me", id=m["id"], format="full")
            .execute()
        )
        hm = header_map(full.get("payload", {}).get("headers") or [])
        pmeta = _partner_meta(hm, partner_emails, partner_domains, partner_names)
        if pmeta.get("is_partner"):
            partner_hits += 1
        subject = hm.get("subject") or "(無題)"
        body = decode_body(full.get("payload") or {})
        text = f"{subject}\n{body}"
        sc, hits = score_text(text, criteria_blob)
        out, reason = clearly_out_of_scope(subject, text, sc)
        if out:
            auto_pass.append(
                _deal_row_from_message(
                    gmail_id=m["id"],
                    source=source,
                    subject=subject,
                    text=text,
                    hm=hm,
                    sc=sc,
                    hits=hits,
                    status="passed",
                    auto_pass_reason=reason,
                    partner_meta=pmeta,
                )
            )
            continue
        keepers.append(
            _deal_row_from_message(
                gmail_id=m["id"],
                source=source,
                subject=subject,
                text=text,
                hm=hm,
                sc=sc,
                hits=hits,
                status="viewing" if sc >= VIEWING_SCORE_MIN else "info",
                partner_meta=pmeta,
            )
        )
    if partner_hits:
        print(
            f"# partner-sourced property mails included: {partner_hits} ({source})",
            file=sys.stderr,
        )
    keepers.sort(key=lambda x: (-(x["match_score"] or 0), x["title"]))
    auto_pass.sort(key=lambda x: (-(x["match_score"] or 0), x["title"]))
    return keepers, auto_pass


def fetch_grok_mails(
    *,
    days: int,
    limit: int,
    criteria_blob: str,
) -> list[dict[str, Any]]:
    """estate 受信箱の [Grok調査] 件名メールを deals 候補化。"""
    svc = gmail_service("token_estate.json")
    q = GROK_QUERY.format(days=days)
    resp = (
        svc.users()
        .messages()
        .list(userId="me", q=q, maxResults=min(limit, 50))
        .execute()
    )
    keepers: list[dict[str, Any]] = []
    for m in resp.get("messages") or []:
        full = (
            svc.users()
            .messages()
            .get(userId="me", id=m["id"], format="full")
            .execute()
        )
        hm = header_map(full.get("payload", {}).get("headers") or [])
        subject = hm.get("subject") or "(無題)"
        if GROK_SUBJECT_PREFIX not in subject:
            continue
        body = decode_body(full.get("payload") or {})
        text = f"{subject}\n{body}"
        grok = parse_grok_report(text)
        sc, hits = score_text(text, criteria_blob)
        sc = grok_match_score(grok, sc)
        listen = str(grok.get("listen_value") or "")
        hazard = str(grok.get("hazard_eval") or "")
        if hazard == "除外" and listen != "聞く":
            status = "passed"
            hits = hits + ["hazard_exclude"]
        elif listen == "見送り" and sc < CANDIDATE_SCORE_MIN:
            status = "passed"
        else:
            status = (
                "viewing"
                if listen == "聞く" or sc >= VIEWING_SCORE_MIN
                else "info"
            )
        row = _deal_row_from_message(
            gmail_id=m["id"],
            source="mail_grok",
            subject=subject,
            text=text,
            hm=hm,
            sc=sc,
            hits=hits + (["grok"] if grok else []),
            status=status,
        )
        sj = dict(row.get("summary_json") or {})
        sj["grok"] = grok
        # inquiry_action → 列にも仮載せ（insert 後に apply_s1_inquiry_fields で確定）
        action = str(grok.get("inquiry_action") or "").strip().lower()
        if action == "portal_sent":
            row["inquiry_status"] = "awaiting_reply"
            sj["inquiry_channel"] = "s1_portal"
        elif action == "kurashift_handoff":
            row["inquiry_status"] = "awaiting_grok"
            sj["inquiry_channel"] = "grok_handoff"
            sj["awaiting_kurashift_first_inquiry"] = True
        row["summary_json"] = sj
        try:
            from jarvis_kurashift_re_inquiry_rules import inquiry_tier_hint

            hint = inquiry_tier_hint(row)
            if hint is not None:
                sj["inquiry_tier_hint"] = hint
                row["summary_json"] = sj
        except Exception:
            pass
        if grok.get("price_man") is not None:
            row["price_man"] = grok["price_man"]
        loc = str(grok.get("location") or "")
        if loc:
            area = next(
                (c for c in CITY_HINTS if c in loc and c not in ("愛知", "岐阜県", "三重")),
                None,
            )
            if area:
                row["area"] = area
        if re.search(r"戸建|戸建て", text):
            row["structure"] = "戸建"
        keepers.append(row)
    keepers.sort(key=lambda x: (-(x["match_score"] or 0), x["title"]))
    return keepers


def existing_gmail_ids(sb: Any) -> set[str]:
    rows = (
        sb.table("kurashift_re_deals")
        .select("summary_json")
        .in_("source", ["mail_admin", "mail_estate", "mail_grok"])
        .limit(500)
        .execute()
    )
    ids: set[str] = set()
    for r in rows.data or []:
        sj = r.get("summary_json") or {}
        gid = sj.get("gmail_id")
        if gid:
            ids.add(gid)
    return ids


def mark_gmail_message_read(
    source: str, gmail_id: str, *, dry_run: bool = False
) -> dict[str, Any]:
    token_name = TOKEN_BY_SOURCE.get(str(source))
    if not token_name:
        return {"ok": False, "error": f"unknown source: {source}"}
    if dry_run:
        return {"ok": True, "dry_run": True, "gmail_id": gmail_id, "source": source}
    svc = gmail_service(token_name)
    svc.users().messages().modify(
        userId="me",
        id=str(gmail_id),
        body={"removeLabelIds": ["UNREAD"]},
    ).execute()
    return {"ok": True, "gmail_id": gmail_id, "source": source}


def mark_deal_gmail_read(sb: Any, deal_id: str, *, dry_run: bool = False) -> dict[str, Any]:
    """案件に紐づく Gmail を既読（UNREAD 除去）。"""
    deal_id = (deal_id or "").strip()
    if not deal_id:
        return {"ok": False, "error": "deal_id required"}
    resp = (
        sb.table("kurashift_re_deals")
        .select("id, title, source, summary_json")
        .eq("id", deal_id)
        .limit(1)
        .execute()
    )
    rows = resp.data or []
    if not rows:
        return {"ok": False, "error": "deal not found"}
    row = rows[0]
    sj = row.get("summary_json") if isinstance(row.get("summary_json"), dict) else {}
    gid = sj.get("gmail_id")
    if not gid:
        return {"ok": True, "skipped": "no_gmail_id", "deal_id": deal_id}
    if sj.get("gmail_read_at"):
        return {
            "ok": True,
            "skipped": "already_read",
            "deal_id": deal_id,
            "gmail_id": gid,
            "gmail_read_at": sj.get("gmail_read_at"),
        }
    source = row.get("source") or sj.get("account") or "mail_admin"
    print(f"使用アカウント: {source} / Gmail API（既読）")
    marked = mark_gmail_message_read(str(source), str(gid), dry_run=dry_run)
    if not marked.get("ok"):
        return {**marked, "deal_id": deal_id}
    if dry_run:
        return {
            "ok": True,
            "dry_run": True,
            "deal_id": deal_id,
            "gmail_id": gid,
            "source": source,
        }
    read_at = datetime.now(timezone.utc).isoformat()
    sj2 = {**sj, "gmail_read_at": read_at}
    sb.table("kurashift_re_deals").update(
        {
            "summary_json": sj2,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
    ).eq("id", deal_id).execute()
    print(f"📎 mark_gmail_read: deal={deal_id} gmail_id={gid} source={source}")
    return {
        "ok": True,
        "deal_id": deal_id,
        "gmail_id": gid,
        "source": source,
        "gmail_read_at": read_at,
    }


def _dedupe_by_gmail(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_id: dict[str, dict[str, Any]] = {}
    for c in rows:
        gid = (c.get("summary_json") or {}).get("gmail_id")
        if not gid:
            continue
        prev = by_id.get(gid)
        if not prev or (c.get("match_score") or 0) > (prev.get("match_score") or 0):
            by_id[gid] = c
    return sorted(by_id.values(), key=lambda x: (-(x["match_score"] or 0), x["title"]))


def _reason_allowlisted(sb: Any, reason: str) -> bool:
    """学習テーブルで allowlisted の理由だけ取込時既読（Phase C）。"""
    reason = (reason or "").strip()
    if not reason:
        return False
    try:
        resp = (
            sb.table("kurashift_auto_pass_learn")
            .select("allowlisted_at, confirm_count, reject_count")
            .eq("reason", reason)
            .limit(1)
            .execute()
        )
        rows = resp.data or []
        if not rows:
            return False
        row = rows[0]
        if row.get("reject_count"):
            return False
        return bool(row.get("allowlisted_at")) and int(row.get("confirm_count") or 0) >= 3
    except Exception:
        return False


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=120)
    ap.add_argument("--limit", type=int, default=40)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--apply", action="store_true", help="kurashift_re_deals へ upsert")
    ap.add_argument(
        "--mark-read-deal-id",
        default="",
        help="案件IDの Gmail を既読（UNREAD除去）。取込と併用しない",
    )
    ap.add_argument(
        "--grok-only",
        action="store_true",
        help="[Grok調査] メールのみ取込（estate）",
    )
    args = ap.parse_args()

    if args.mark_read_deal_id:
        sb = sb_client()
        result = mark_deal_gmail_read(sb, args.mark_read_deal_id, dry_run=args.dry_run)
        print(f"KURASHIFT_RESULT:{json.dumps(result, ensure_ascii=False)}")
        if not result.get("ok"):
            return 1
        return 0

    if not args.apply:
        args.dry_run = True

    print("使用アカウント: admin（主）+ estate（補完）+ mail_grok（estate） / Gmail API")
    sb = sb_client()
    criteria_blob = load_criteria_blob(sb)
    candidates: list[dict[str, Any]] = []
    auto_pass_all: list[dict[str, Any]] = []
    if not args.grok_only:
        for token, source in (
            ("token_livingsupport.json", "mail_admin"),
            ("token_estate.json", "mail_estate"),
        ):
            try:
                keepers, auto_pass = fetch_account(
                    token, source, days=args.days, limit=args.limit, criteria_blob=criteria_blob
                )
                print(
                    f"# {source}: candidates={len(keepers)} auto_pass={len(auto_pass)}"
                )
                candidates.extend(keepers)
                auto_pass_all.extend(auto_pass)
            except Exception as e:
                print(f"# {source}: FAIL {type(e).__name__}: {e}")
    try:
        grok_rows = fetch_grok_mails(
            days=args.days, limit=args.limit, criteria_blob=criteria_blob
        )
        print(f"# mail_grok: candidates={len(grok_rows)}")
        candidates.extend(grok_rows)
    except Exception as e:
        print(f"# mail_grok: FAIL {type(e).__name__}: {e}")

    uniq = _dedupe_by_gmail(candidates)
    uniq_pass = _dedupe_by_gmail(auto_pass_all)
    keep_ids = {(c.get("summary_json") or {}).get("gmail_id") for c in uniq}
    uniq_pass = [
        c
        for c in uniq_pass
        if (c.get("summary_json") or {}).get("gmail_id") not in keep_ids
    ]
    print(f"# unique_candidates={len(uniq)} unique_auto_pass={len(uniq_pass)}")
    for c in uniq[:12]:
        print(
            f"  - [{c['match_score']}] {c['source']} {c.get('area') or '-'} {c['title'][:70]}"
        )
    for c in uniq_pass[:8]:
        reason = (c.get("summary_json") or {}).get("auto_pass_reason")
        print(
            f"  × auto_pass[{reason}] [{c['match_score']}] {c['source']} {c['title'][:60]}"
        )

    if args.dry_run and not args.apply:
        print(
            "📎 property_mail_match: dry-run（--apply で deals 反映・"
            "auto_pass は未既読／allowlist理由のみ既読）"
        )
        print(
            "KURASHIFT_RESULT:"
            + json.dumps(
                {
                    "candidates": len(uniq),
                    "auto_pass": len(uniq_pass),
                    "dry_run": True,
                },
                ensure_ascii=False,
            )
        )
        return 0

    seen = existing_gmail_ids(sb)
    inserted = 0
    for c in uniq:
        gid = (c.get("summary_json") or {}).get("gmail_id")
        if gid in seen:
            continue
        ins = sb.table("kurashift_re_deals").insert(c).execute()
        inserted += 1
        if gid:
            seen.add(gid)
        try:
            from jarvis_kurashift_deal_events import insert_deal_event

            new_id = (ins.data or [{}])[0].get("id")
            if new_id:
                et = "grok_applied" if c.get("source") == "mail_grok" else "created"
                insert_deal_event(
                    sb,
                    deal_id=str(new_id),
                    event_type=et,
                    summary=f"取込: {c.get('title', '')[:80]}",
                    actor="jarvis",
                    to_status=str(c.get("status") or "info"),
                    payload={"source": c.get("source"), "match_score": c.get("match_score")},
                )
                if c.get("source") == "mail_grok":
                    grok = (c.get("summary_json") or {}).get("grok") or {}
                    if isinstance(grok, dict) and grok.get("inquiry_action"):
                        try:
                            apply_s1_inquiry_fields(
                                sb,
                                deal_id=str(new_id),
                                grok=grok,
                                gmail_id=str(gid) if gid else None,
                            )
                        except Exception as e:
                            print(
                                f"# s1_inquiry_apply FAIL {new_id}: {type(e).__name__}: {e}"
                            )
        except Exception:
            pass

    auto_inserted = 0
    auto_read = 0
    for c in uniq_pass:
        gid = (c.get("summary_json") or {}).get("gmail_id")
        if not gid or gid in seen:
            continue
        sj = dict(c.get("summary_json") or {})
        # Phase A: 取込時は既読にしない。学習確認後のみ既読。
        sj["auto_pass_pending_read"] = True
        sj.pop("gmail_read_at", None)
        row = {**c, "summary_json": sj, "status": "passed"}
        # allowlist 済み理由だけ自動既読（Phase C）
        reason = str(sj.get("auto_pass_reason") or "")
        if reason and _reason_allowlisted(sb, reason):
            try:
                read_at = datetime.now(timezone.utc).isoformat()
                mark_gmail_message_read(str(c.get("source") or "mail_admin"), str(gid))
                sj["gmail_read_at"] = read_at
                sj["auto_pass_pending_read"] = False
                sj["auto_pass_allowlisted_read"] = True
                row["summary_json"] = sj
                auto_read += 1
            except Exception as e:
                print(f"# allowlisted mark-read FAIL {gid}: {type(e).__name__}: {e}")
                sj.pop("gmail_read_at", None)
                sj["auto_pass_pending_read"] = True
                row["summary_json"] = sj
        sb.table("kurashift_re_deals").insert(row).execute()
        auto_inserted += 1
        seen.add(gid)

    promoted = 0
    existing = (
        sb.table("kurashift_re_deals")
        .select("id, status, match_score")
        .eq("status", "info")
        .limit(500)
        .execute()
    )
    for row in existing.data or []:
        sc = float(row.get("match_score") or 0)
        if sc >= VIEWING_SCORE_MIN:
            sb.table("kurashift_re_deals").update(
                {"status": "viewing", "updated_at": datetime.now(timezone.utc).isoformat()}
            ).eq("id", row["id"]).execute()
            promoted += 1
    print(
        f"📎 property_mail_match: inserted={inserted} "
        f"auto_pass_inserted={auto_inserted} auto_pass_marked_read={auto_read} "
        f"skipped_existing={len(uniq) + len(uniq_pass) - inserted - auto_inserted} "
        f"promoted_to_viewing={promoted}"
    )
    print(
        "KURASHIFT_RESULT:"
        + json.dumps(
            {
                "inserted": inserted,
                "auto_pass_inserted": auto_inserted,
                "auto_pass_marked_read": auto_read,
                "promoted": promoted,
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
