#!/usr/bin/env python3
"""神大家運営相談フォーム（1906a1a5）下書き・不足チェック。

  cd ~/git-repos && set -a && source .env.jarvis_private && set +a
  ~/selenium_env/venv/bin/python scripts/jarvis_kurashift_re_ops_form_draft.py --deal-id <uuid>
  ~/selenium_env/venv/bin/python scripts/jarvis_kurashift_re_ops_form_draft.py --deal-id <uuid> --apply

送信はしない（jarvis-outbound-confirm）。フォーム URL のみ案内。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

REPO = Path(__file__).resolve().parents[1]
FORM_YAML = REPO / "config" / "kurashift_re_ops_form_1906a1a5.yaml"
S1_PROFILE_YAML = REPO / "config" / "grok_s1_inquiry_profile.yaml"
ATTACH_ROOT = REPO / ".jarvis_state" / "kurashift_re_deal_attachments"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def sb_client() -> Any:
    url = os.environ.get("JARVIS_SUPABASE_URL")
    key = os.environ.get("JARVIS_SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        raise SystemExit("JARVIS_SUPABASE_URL / JARVIS_SUPABASE_SERVICE_ROLE_KEY が必要です")
    from supabase import create_client

    return create_client(url, key)


def load_form_config() -> dict[str, Any]:
    return yaml.safe_load(FORM_YAML.read_text(encoding="utf-8")) or {}


def _sj(deal: dict[str, Any]) -> dict[str, Any]:
    sj = deal.get("summary_json")
    return sj if isinstance(sj, dict) else {}


def _grok(deal: dict[str, Any]) -> dict[str, Any]:
    g = _sj(deal).get("grok")
    return g if isinstance(g, dict) else {}


def _inquiry_status(deal: dict[str, Any]) -> str:
    if deal.get("inquiry_status"):
        return str(deal["inquiry_status"])
    return str(_sj(deal).get("inquiry_status") or "none")


def _suggest_folder_name(deal: dict[str, Any]) -> str:
    title = str(deal.get("title") or "").strip()
    if title:
        return title[:80]
    area = str(deal.get("area") or "").strip()
    price = deal.get("price_man")
    if area and price is not None:
        return f"{area}{price}万円"
    return "（物件名を決めてDriveフォルダ名と一致させる）"


def _s3(deal: dict[str, Any]) -> dict[str, Any]:
    s = _sj(deal).get("s3_investigation")
    return s if isinstance(s, dict) else {}


def _overrides(deal: dict[str, Any]) -> dict[str, str]:
    raw = _sj(deal).get("ops_form_overrides")
    if not isinstance(raw, dict):
        return {}
    out: dict[str, str] = {}
    for k, v in raw.items():
        if v is None:
            continue
        s = str(v).strip()
        if s:
            out[str(k)] = s
    return out


def _load_own_funds() -> str | None:
    if not S1_PROFILE_YAML.is_file():
        return None
    text = S1_PROFILE_YAML.read_text(encoding="utf-8")
    snap: dict[str, Any] | None = None
    try:
        data = yaml.safe_load(text) or {}
        if isinstance(data, dict) and isinstance(data.get("profile_snapshot"), dict):
            snap = data["profile_snapshot"]
    except Exception:
        snap = None
    if snap is None:
        # YAML 全体が壊れていても snapshot だけ拾う
        m = re.search(
            r"profile_snapshot:\s*\n((?:[ \t]+.+\n)+)",
            text,
        )
        if m:
            try:
                snap = yaml.safe_load("profile_snapshot:\n" + m.group(1))
                if isinstance(snap, dict):
                    snap = snap.get("profile_snapshot")  # type: ignore[assignment]
            except Exception:
                snap = None
        if not isinstance(snap, dict):
            m2 = re.search(r"own_funds_manyen:\s*(\d+)", text)
            if not m2:
                return None
            manyen = int(m2.group(1))
            m3 = re.search(r'checked_at:\s*"?([0-9-]+)"?', text)
            checked = m3.group(1) if m3 else ""
            base = f"約{manyen}万円（S1 profile snapshot）"
            return f"{base}・確認日{checked}" if checked else base
    if not isinstance(snap, dict):
        return None
    manyen = snap.get("own_funds_manyen")
    if manyen is None:
        return None
    checked = str(snap.get("checked_at") or "").strip()
    base = f"約{manyen}万円（S1 profile snapshot）"
    return f"{base}・確認日{checked}" if checked else base


def _extract_gas_from_attachments(deal_id: str) -> str | None:
    """物件概要書PDFからガス欄を読む（調査中含む）。"""
    root = ATTACH_ROOT / deal_id
    if not root.is_dir():
        return None
    try:
        import fitz  # type: ignore
    except Exception:
        return None

    texts: list[str] = []
    for pdf in sorted(root.glob("*.pdf")):
        name = pdf.name
        if "概要" not in name and "物件" not in name:
            continue
        try:
            doc = fitz.open(pdf)
            texts.append("\n".join((page.get_text() or "") for page in doc))
        except Exception:
            continue
    if not texts:
        for pdf in sorted(root.glob("*.pdf"))[:3]:
            try:
                doc = fitz.open(pdf)
                texts.append("\n".join((page.get_text() or "") for page in doc))
            except Exception:
                continue
    blob = "\n".join(texts)
    if not blob.strip():
        return None
    if "プロパン" in blob or re.search(r"\bLPG?\b", blob):
        return "プロパンガス（概要書）"
    if "都市ガス" in blob:
        return "都市ガス（概要書）"
    # 「ガ ス」「ガス」の直後〜数行
    m = re.search(r"ガ\s*ス\s*([^\n]{0,40})", blob)
    if m:
        frag = m.group(1).strip()
        if "調査中" in frag or "調査中" in blob[m.start() : m.start() + 80]:
            return "調査中（物件概要書記載）"
        if frag and frag not in ("電 気", "電気"):
            return frag
    if "調査中" in blob and "ガ" in blob:
        return "調査中（物件概要書記載）"
    return None


def merge_overrides(
    deal: dict[str, Any], sets: dict[str, str], *, clear: bool = False
) -> dict[str, str]:
    cur = {} if clear else _overrides(deal)
    for k, v in sets.items():
        k = str(k).strip()
        v = str(v).strip()
        if not k:
            continue
        if v == "" or v.lower() in ("-", "clear", "unset"):
            cur.pop(k, None)
        else:
            cur[k] = v
    return cur


def suggested_fillables(deal: dict[str, Any]) -> dict[str, str]:
    """ユーザー判断が薄い項目の提案値（未設定のときだけ使う）。"""
    out: dict[str, str] = {}
    folder = _suggest_folder_name(deal)
    funds = _load_own_funds()
    if funds:
        out["self_funds"] = funds
    gas = _extract_gas_from_attachments(str(deal.get("id") or ""))
    if gas:
        out["gas"] = gas
    out["viewing_done"] = "未内見（内見しながら修繕見立てを確認していく）"
    out["planning_aligned"] = (
        "はい（築古戸建本線・土地値大幅超。想定利回りは本線帯の下限寄り）"
    )
    out["urgency"] = "本番（内見・購入判断のための運営相談）"
    out["purchase_purpose"] = "築古戸建のCF構築・共同担保原資（神大家プランニング）"
    out["offer_price"] = "未定（買付前・運営相談後に決定）"
    out["loan_terms"] = (
        "名古屋銀行＋愛知県信用保証協会想定（本体も名銀）。"
        "土地値約390%／評価概算約1,873万のためフル〜オーバーローン狙い。"
        "過去事例（WeStudy・塾内）: 名銀瀬戸・豊山町戸建 約2.375〜2.4%・20年・オーバー実行、"
        "協会フルローン仮で20年確認（森下）、名銀高蔵寺は協会付き可・15年（金利失念）。"
        "本案件の見立て: 金利約2.4%・期間20年・借入は購入480＋修繕150＝約630万前後"
        "（諸経費込みで〜700万のオーバー幅を講師・名銀に確認）。保証料率目安約1.15%（豊山事例）"
    )
    # 買い進めプラン（★251124）築古戸建の標準: リフォーム額150万／後利回り約15.6%
    # 動画・事例は内訳の参考（外壁〜100万等）。2棟でも闇雲に倍積みしない。
    out["repair_exterior"] = (
        "約50〜80万円（最低限の雨漏り・外壁・屋根。フル塗装は山積みせず。"
        "グルコン事例の外壁塗装〜100万は上限参考）"
    )
    out["repair_interior"] = (
        "約70〜100万円（入居付け用水回り・クロス・床等。"
        "AP動画の1室基本リフォーム〜80万を戸建1棟相当の上限感として参照）"
    )
    out["repair_total_yield"] = (
        "総額約150万円（買い進めプラン築古戸建の標準想定）。"
        "2棟だが本線は150・実額増は内見で確認（上限感〜250）。"
        "家賃本線年60万÷(480+150)≒表面約9.5%（プラン目標15%帯には未達→要確認）"
    )
    out["monthly_cf"] = (
        "概算＋約1.4万円/月（家賃本線5万−管理5%−名銀協会ローン630万・2.4%・20年で月約3.3万）。"
        "本体480のみなら月返済約2.5万・CF約＋2.2万。"
        "保証料・固都税・空室は別途。内見・仮審査後に再計算"
    )
    out["building_residual"] = (
        "ほぼ0〜僅少見立て（旧耐震・軽量鉄骨。土地値主導で建物残価値は小さく見る）"
    )
    # drive_folder は URL が無いと提案しない
    _ = folder
    return out

def _build_instructor_questions(
    deal: dict[str, Any], form_field: dict[str, Any]
) -> str | None:
    """デフォルト3点 + S3ヒアリング + 戸建固有を統合。"""
    default = str(form_field.get("default_template") or "").strip()
    s3 = _s3(deal)
    grok = _grok(deal)
    hearing = s3.get("hearing_questions") or []
    if not isinstance(hearing, list):
        hearing = []

    lines: list[str] = []
    if default:
        lines.append(default.rstrip())
    if hearing:
        lines.append("")
        lines.append("【詳細調査（S3）ヒアリング】")
        for i, q in enumerate(hearing, 1):
            q = str(q).strip()
            if q:
                lines.append(f"{i}. {q}")

    kodate_extras: list[str] = []
    building = str(grok.get("building") or s3.get("structure") or "")
    if "戸建" in str(deal.get("structure") or "") or "戸建" in building or "2棟" in str(
        deal.get("title") or ""
    ):
        if "間取り" in " ".join(str(x) for x in hearing) or "間取" in building:
            pass
        else:
            kodate_extras.append("間取り・専有・水回りが未確認の場合の修繕・家賃見立ての見方")
        if any("旧耐震" in str(x) or "1975" in str(x) or "軽量鉄骨" in str(x) for x in hearing) or (
            "旧耐震" in building or "1975" in building
        ):
            kodate_extras.append("旧耐震／軽量鉄骨戸建としての修繕目安と購入可否の数字感")
        if any("土砂" in str(x) or "ハザード" in str(x) for x in hearing) or "注意" in str(
            grok.get("hazard_eval") or ""
        ):
            kodate_extras.append("ハザード（土砂・洪水等）が内見判断にどう効くか")
        land = str(grok.get("land100_ratio") or "")
        if land:
            kodate_extras.append(f"土地値{land}の見方と、買付前に確認すべき接道・境界の有無")

    if kodate_extras:
        lines.append("")
        lines.append("【戸建固有・追加確認】")
        for x in kodate_extras:
            lines.append(f"・{x}")
        lines.append(
            "・買い進めプラン標準のリフォーム約150万円前後で足りるか"
            "（2棟でも闇雲に倍積みせず、内見で優先順位を切る前提でよいか）"
        )
        lines.append(
            "・修繕後利回りがプラン目標15%帯に届かない場合、"
            "減額・家賃上方・修繕圧縮のどれを優先すべきか"
        )
        lines.append(
            "・土地値約390%を根拠に、名古屋銀行＋愛知県保証協会で"
            "本体フル〜オーバー（購入＋修繕〜630万前後・2.4%・20年見立て）は現実的か"
        )
        lines.append(
            "・協会付きの期間が15年止めになった場合のCF・買う／見送りの目安"
        )

    out = "\n".join(lines).strip()
    return out or (default or None)


def _reply_value(field: dict[str, Any], deal: dict[str, Any], grok: dict[str, Any]) -> str | None:
    """reply tier: Grok / S3 から埋められるものを埋める。"""
    fid = str(field.get("id") or "")
    s3 = _s3(deal)
    building = str(grok.get("building") or s3.get("structure") or "")
    if fid == "nearest_station":
        pop = str(grok.get("population_table") or "").strip()
        if pop:
            return pop.split("·")[0].strip() if "·" in pop else pop
        return None
    if fid == "building_age":
        m = re.search(r"築(\d{4})", building)
        if m:
            year = int(m.group(1))
            age = max(0, datetime.now().year - year)
            return f"築{age}年（{year}年）"
        m2 = re.search(r"(19\d{2}|20\d{2})", building)
        if m2:
            year = int(m2.group(1))
            return f"築{max(0, datetime.now().year - year)}年（{year}年）"
        return None
    if fid == "occupancy":
        if "空室" in building:
            return "空室"
        if "入居" in building or "満室" in building:
            return "入居中"
        return None
    if fid == "land_sqm":
        la = grok.get("land_area")
        return str(la).strip() if la else None
    if fid == "building_sqm":
        m = re.search(r"([\d.]+)\s*㎡", building)
        return f"{m.group(1)}㎡" if m else None
    if fid == "gas":
        # S3 / grok 本文にプロパン等があれば
        blob = f"{building} {s3.get('structure') or ''} {s3.get('verdict_reason') or ''}"
        if "プロパン" in blob or "LP" in blob:
            return "プロパンガス"
        if "都市ガス" in blob:
            return "都市ガス"
        return _extract_gas_from_attachments(str(deal.get("id") or ""))
    if fid == "transaction_type":
        note = str(grok.get("inquiry_note") or _sj(deal).get("inquiry_note") or "")
        if "売主" in note or "AlbaLink" in note or "アルバ" in note:
            return "売主"
        return None
    if fid == "annual_rent" or fid == "gross_yield":
        rent = str(s3.get("expected_rent") or "").strip()
        return rent or None
    if fid == "structure_rooms":
        struct = str(deal.get("structure") or "").strip()
        persona = s3.get("persona") if isinstance(s3.get("persona"), dict) else {}
        layout = str((persona or {}).get("layout") or "")
        parts = [p for p in [struct, building[:80] if building else "", layout] if p]
        return " / ".join(parts) if parts else None
    return None


def _auto_value(field: dict[str, Any], deal: dict[str, Any], grok: dict[str, Any]) -> str | None:
    fid = field.get("id")
    src = field.get("source")
    if field.get("env"):
        for key in field["env"]:
            val = (os.environ.get(str(key)) or "").strip()
            if val:
                return val
        return None
    if src == "deal.title":
        return str(deal.get("title") or "").strip() or None
    if src == "deal.price_man":
        pm = deal.get("price_man")
        return f"{pm}万円" if pm is not None else None
    if src == "deal.yield_pct":
        y = deal.get("yield_pct")
        yi = _sj(deal).get("yield_info")
        if isinstance(yi, dict) and yi.get("label"):
            return str(yi["label"])
        return f"表面利回り{y}%" if y is not None else None
    if src == "deal.structure":
        # structure_rooms は reply_value も試す
        rv = _reply_value({**field, "id": "structure_rooms"}, deal, grok)
        if rv:
            return rv
        s = str(deal.get("structure") or "").strip()
        return s or None
    if src == "deal.source":
        src_val = str(deal.get("source") or "")
        if src_val in ("mail_grok", "kenbiya", "rakumachi"):
            return f"いいえ（source={src_val}。該当時のみはい）"
        return "いいえ"
    if src == "grok.land100":
        parts = []
        if grok.get("land100"):
            parts.append(str(grok["land100"]))
        ratio = grok.get("land100_ratio") or _sj(deal).get("land100_ratio")
        if ratio:
            parts.append(str(ratio))
        if grok.get("route_price_tsubo"):
            parts.append(f"路線価:{grok['route_price_tsubo']}")
        if grok.get("land_method"):
            parts.append(str(grok["land_method"]))
        if grok.get("land_appraisal_man"):
            parts.append(f"評価概算:{grok['land_appraisal_man']}万円")
        return " / ".join(parts) if parts else None
    if src == "grok.hazard_eval":
        parts = []
        if grok.get("hazard_eval"):
            parts.append(f"HZ:{grok['hazard_eval']}")
        if grok.get("hazard_flood"):
            parts.append(f"洪水:{grok['hazard_flood']}")
        if grok.get("hazard_landslide"):
            parts.append(f"土砂:{grok['hazard_landslide']}")
        if grok.get("reason_line"):
            parts.append(str(grok["reason_line"])[:120])
        return " · ".join(parts) if parts else None
    if src == "grok.parking":
        return str(grok.get("parking") or "").strip() or None
    if fid == "property_name":
        return _suggest_folder_name(deal)
    if fid == "gross_yield":
        return _reply_value({"id": "gross_yield"}, deal, grok)
    return None


def count_attachments(deal_id: str, sb: Any) -> int:
    n = 0
    try:
        r = (
            sb.table("kurashift_re_deal_attachments")
            .select("id", count="exact")
            .eq("deal_id", deal_id)
            .execute()
        )
        n = int(getattr(r, "count", None) or 0)
    except Exception:
        pass
    local = ATTACH_ROOT / deal_id
    if local.is_dir():
        n = max(n, len(list(local.glob("*.pdf"))))
    return n


def build_form_draft(
    deal: dict[str, Any],
    *,
    attach_count: int = 0,
    form_cfg: dict[str, Any] | None = None,
    use_suggestions: bool = False,
) -> dict[str, Any]:
    cfg = form_cfg or load_form_config()
    form_url = str(cfg.get("form_url") or "https://form.os7.biz/f/1906a1a5/")
    grok = _grok(deal)
    fields_cfg = cfg.get("fields") or []
    overrides = _overrides(deal)
    suggestions = suggested_fillables(deal) if use_suggestions else {}

    filled: list[dict[str, str]] = []
    missing: list[str] = []
    lines: list[str] = [
        f"📎 運営相談フォーム下書き — {deal.get('title', '')[:60]}",
        f"deal_id: {deal.get('id')}",
        f"問合せ: {_inquiry_status(deal)}",
        f"フォーム: {form_url}",
        "",
        "【自動・下書き済】",
    ]

    for f in fields_cfg:
        if not isinstance(f, dict):
            continue
        fid = str(f.get("id") or "")
        label = str(f.get("label") or fid)
        tier = str(f.get("tier") or "manual")
        val = None
        src_tag = ""
        if fid and fid in overrides:
            val = overrides[fid]
            src_tag = "override"
        elif tier == "auto":
            val = _auto_value(f, deal, grok)
            src_tag = "auto"
        elif tier == "reply":
            val = _reply_value(f, deal, grok)
            src_tag = "reply"
        elif tier == "research":
            if fid in ("annual_rent", "gross_yield"):
                val = _reply_value(f, deal, grok)
                src_tag = "reply"
            elif fid == "self_funds":
                val = _load_own_funds()
                src_tag = "profile"
            elif fid == "loan_terms" and use_suggestions:
                val = suggestions.get(fid)
                src_tag = "suggest"
            elif use_suggestions and fid in suggestions:
                val = suggestions.get(fid)
                src_tag = "suggest"
        elif tier == "manual":
            if fid == "questions_for_instructor":
                val = _build_instructor_questions(deal, f)
                src_tag = "template"
            elif use_suggestions and fid in suggestions:
                val = suggestions.get(fid)
                src_tag = "suggest"

        if val:
            filled.append(
                {
                    "id": fid,
                    "label": label,
                    "value": val,
                    "source": src_tag or "unknown",
                }
            )
            prefix = f"[{src_tag}] " if src_tag in ("override", "suggest", "profile") else ""
            lines.append(f"  · {prefix}{label}: {val[:200]}")
        elif tier in ("research", "reply", "manual"):
            missing.append(label)

    if attach_count <= 0:
        missing.append("神大家個人Driveへの写真・図面格納（PDF添付0件）")
    else:
        drive_ok = bool(overrides.get("drive_folder"))
        note = "Drive URL反映済" if drive_ok else "ローカルPDFあり・Driveへも展開要"
        lines.append(f"  · 添付PDF: {attach_count}件（{note}）")

    lines.extend(["", "【要調査・要入力】"])
    if not missing:
        lines.append("  （なし）")
    for m in missing[:20]:
        lines.append(f"  ⚠ {m}")
    if len(missing) > 20:
        lines.append(f"  …他 {len(missing) - 20} 項目")

    lines.extend(
        [
            "",
            "【次の一手】",
            "1. 上記⚠を調べて記入（家賃相場・修繕試算・CF）",
            "2. 神大家個人Driveに物件フォルダ＋写真（フォルダ名＝物件名）",
            f"3. フォーム入力 → 確認後送信 → {form_url}",
            "4. 809 運営回答後、内見判断",
            "",
            "上書き例:",
            "  … --set drive_folder='URL／フォルダ名' --set urgency=練習 --apply",
            "  … --fill-suggestions --apply  # 判断項目の提案値を一括埋込",
        ]
    )

    markdown = "\n".join(lines)
    return {
        "ok": True,
        "deal_id": deal.get("id"),
        "form_url": form_url,
        "filled_count": len(filled),
        "missing_count": len(missing),
        "missing": missing,
        "filled": filled,
        "overrides": overrides,
        "attach_count": attach_count,
        "markdown": markdown,
        "generated_at": now_iso(),
    }


def persist_draft(
    sb: Any,
    deal_id: str,
    draft: dict[str, Any],
    *,
    overrides: dict[str, str] | None = None,
) -> None:
    deal = (
        sb.table("kurashift_re_deals")
        .select("summary_json")
        .eq("id", deal_id)
        .maybe_single()
        .execute()
    ).data
    if not deal:
        raise SystemExit(f"deal not found: {deal_id}")
    sj = deal.get("summary_json") if isinstance(deal.get("summary_json"), dict) else {}
    if overrides is not None:
        sj["ops_form_overrides"] = overrides
    sj["ops_form_draft"] = {
        "at": draft.get("generated_at"),
        "form_url": draft.get("form_url"),
        "missing_count": draft.get("missing_count"),
        "filled_count": draft.get("filled_count"),
        "missing": draft.get("missing"),
        "filled": draft.get("filled"),
        "markdown": draft.get("markdown"),
    }
    sb.table("kurashift_re_deals").update(
        {"summary_json": sj, "updated_at": now_iso()}
    ).eq("id", deal_id).execute()


def _parse_set_args(items: list[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for item in items:
        if "=" not in item:
            raise SystemExit(f"--set は id=値 形式: {item}")
        k, v = item.split("=", 1)
        out[k.strip()] = v.strip()
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="神大家運営相談フォーム下書き")
    ap.add_argument("--deal-id", required=True)
    ap.add_argument("--apply", action="store_true", help="summary_json.ops_form_draft へ保存")
    ap.add_argument(
        "--set",
        action="append",
        default=[],
        metavar="ID=VALUE",
        help="ops_form_overrides に保存（複数可）。空値/- で解除",
    )
    ap.add_argument(
        "--fill-suggestions",
        action="store_true",
        help="自己資金・ガス・プラン適合・至急度・修繕未試算などの提案値を override にマージ",
    )
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    sys.path.insert(0, str(REPO / "scripts"))
    from jarvis_kurashift_re_inquiry import get_deal  # noqa: E402

    sb = sb_client()
    deal = get_deal(sb, args.deal_id)

    sets = _parse_set_args(args.set)
    if args.fill_suggestions:
        sug = suggested_fillables(deal)
        # 既存 override を優先（上書きしない）
        for k, v in sug.items():
            sets.setdefault(k, v)

    new_overrides = None
    if sets:
        new_overrides = merge_overrides(deal, sets)
        sj = _sj(deal)
        sj = dict(sj)
        sj["ops_form_overrides"] = new_overrides
        deal = dict(deal)
        deal["summary_json"] = sj

    attach_count = count_attachments(args.deal_id, sb)
    draft = build_form_draft(
        deal,
        attach_count=attach_count,
        use_suggestions=False,  # 提案は --fill-suggestions で override 化済み
    )

    print(draft["markdown"])
    if args.apply:
        persist_draft(sb, args.deal_id, draft, overrides=new_overrides)
        print(f"# ops_form_draft saved to deal {args.deal_id[:8]}…")
        if new_overrides is not None:
            print(f"# overrides: {len(new_overrides)} keys")

    print("KURASHIFT_RESULT:" + json.dumps(draft, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
