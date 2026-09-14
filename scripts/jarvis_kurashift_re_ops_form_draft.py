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


def _strip_grok_prefix(title: str) -> str:
    """物件名から [Grok調査] 等の接頭辞を除く。"""
    t = str(title or "").strip()
    t = re.sub(r"^\[Grok調査\]\s*", "", t)
    t = re.sub(r"^【Grok調査】\s*", "", t)
    return t.strip() or t


def _suggest_folder_name(deal: dict[str, Any]) -> str:
    title = _strip_grok_prefix(str(deal.get("title") or ""))
    if title:
        return title[:80]
    area = str(deal.get("area") or "").strip()
    price = deal.get("price_man")
    if area and price is not None:
        return f"{area}{price}万円"
    return "物件名未定"


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


def _zaim_tameru_yen() -> tuple[int | None, str]:
    """Zaim『貯める』の金額が取れれば返す。不明なら (None, note)。

    CSV からは口座名ヒットだけで残高が取れないため、現状は常に None
    （フォールバック＝銀行残高合計）。
    """
    return None, "Zaim『貯める』残高不明"


def _zaim_bank_total_yen(sb: Any | None = None) -> tuple[int, str]:
    """liquidity_snapshots の銀行口座残高合計（money-ops と同系）。"""
    try:
        client = sb or sb_client()
        acc_rows = (
            client.table("liquidity_accounts")
            .select("id,name,kind,active")
            .eq("active", True)
            .eq("kind", "bank")
            .execute()
        )
        snap_rows = (
            client.table("liquidity_snapshots")
            .select("account_id,as_of,balance_jpy")
            .order("as_of", desc=True)
            .limit(120)
            .execute()
        )
    except Exception as e:
        return 0, f"銀行残高取得失敗:{type(e).__name__}"
    bank_ids = {str(a["id"]): str(a.get("name") or a["id"]) for a in (acc_rows.data or [])}
    if not bank_ids:
        return 0, "銀行口座未登録"
    latest: dict[str, dict[str, Any]] = {}
    for row in snap_rows.data or []:
        aid = str(row.get("account_id") or "")
        if aid not in bank_ids or aid in latest:
            continue
        latest[aid] = row
    total = int(sum(float(v.get("balance_jpy") or 0) for v in latest.values()))
    as_of = max((str(v.get("as_of") or "") for v in latest.values()), default="")
    n = len(latest)
    note = f"銀行残高合計 約{total // 10000}万円（{n}口座"
    if as_of:
        note += f"・{as_of}"
    note += "）"
    return total, note


def _policy_loan_usable_yen(sb: Any | None = None) -> tuple[int, str]:
    """契約者貸付の残高（次物件キープとして使える額の目安）。"""
    try:
        client = sb or sb_client()
        r = (
            client.table("portfolio_snapshots")
            .select("account_id,as_of,value_jpy,note")
            .order("as_of", desc=True)
            .limit(80)
            .execute()
        )
    except Exception as e:
        return 0, f"保険貸付スナップ取得失敗:{type(e).__name__}"
    latest: dict[str, dict[str, Any]] = {}
    for row in r.data or []:
        aid = str(row.get("account_id") or "")
        if "policy_loan" not in aid:
            continue
        if aid not in latest:
            latest[aid] = row
    total = int(sum(float(v.get("value_jpy") or 0) for v in latest.values()))
    as_of = max((str(v.get("as_of") or "") for v in latest.values()), default="")
    note = f"契約者貸付残高 約{total // 10000}万円"
    if as_of:
        note += f"（{as_of}）"
    return total, note


def _load_own_funds(sb: Any | None = None) -> str | None:
    """自己資金 = （貯める or 銀行合計）＋保険契約者貸付。

    フォームには合計のみ（内訳は記載しない）。
    貯めるが不明なときは銀行口座残高合計を使う。
    """
    tameru_yen, _tameru_note = _zaim_tameru_yen()
    loan_yen, _loan_note = _policy_loan_usable_yen(sb)
    total = 0
    if tameru_yen is not None and tameru_yen > 0:
        total += tameru_yen
    else:
        bank_yen, _bank_note = _zaim_bank_total_yen(sb)
        if bank_yen > 0:
            total += bank_yen
    if loan_yen > 0:
        total += loan_yen
    if total > 0:
        return f"約{total // 10000}万円"
    return "要確認"


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
    """ユーザー判断が薄い項目の提案値（記載例レベル・改行）。"""
    out: dict[str, str] = {}
    funds = _load_own_funds()
    if funds:
        out["self_funds"] = funds
    gas = _extract_gas_from_attachments(str(deal.get("id") or ""))
    if gas:
        out["gas"] = gas
    out["viewing_done"] = "未内見"
    out["planning_aligned"] = "はい"
    out["urgency"] = "本番\n・競合もいるので、急ぎたいです。"
    out["purchase_purpose"] = "a）長期所有目的（CF獲得目的）"
    out["offer_price"] = "未定"
    out["loan_terms"] = (
        "名古屋銀行＋愛知県信用保証協会\n"
        "20年 2.4%\n"
        "借入約630万円（購入480＋修繕150）\n"
        "月返済約3.3万円"
    )
    out["repair_exterior"] = (
        "TOTAL 50〜80万円想定\n"
        "内訳：\n"
        "雨漏り・屋根補修\n"
        "外壁最低限"
    )
    out["repair_interior"] = (
        "TOTAL 70〜100万円想定\n"
        "内訳：\n"
        "水回り・クロス・床（入居付け）"
    )
    out["repair_total_yield"] = (
        "修繕費総額 約150万円\n"
        "想定修繕後利回り 約14%"
    )
    out["monthly_cf"] = (
        "月家賃7.4万 − 月返済約3.3万 − 諸経費0.74万\n"
        "≒ 月CF 約＋3.4万円"
    )
    out["building_residual"] = "0"
    out["annual_rent"] = (
        "近隣類似・住宅扶助上限より\n"
        "単身3.7万円×2棟＝月7.4万円\n"
        "年88.8万円"
    )
    out["gross_yield"] = "表面利回り約18.5%、月家賃7.4万円"
    return out


def _build_instructor_questions(
    deal: dict[str, Any], form_field: dict[str, Any]
) -> str | None:
    """記入例どおり短く（詳細ヒアリングは運営回答後にメールで補足）。"""
    _ = deal
    default = str(form_field.get("default_template") or "").strip()
    return default or (
        "以下を確認したいです。\n"
        "・戸建て初めてでやや遠い物件なので、内見に値する物件か見解を聞きたいです。\n"
        "・土地値が高いので、共同担保に使用できるのであれば購入を進める価値があると考えています。"
        "今回の物件は三井住友L&F（L&Fアセットファイナンス）の共同担保に使えそうでしょうか。\n"
        "・講座で、L&Fは支店エリア外だと共同担保に使えない／評価が出ない、と理解しています。"
        "豊川市御油は名古屋支店の対象エリアに入るかも合わせてご確認をお願い致します。\n"
        "・概算修繕費が概ね合っているか、他に注意点はないか。\n"
        "ご確認をお願い致します。"
    )


def _reply_value(field: dict[str, Any], deal: dict[str, Any], grok: dict[str, Any]) -> str | None:
    """reply tier: Grok / S3 から埋められるものを埋める。"""
    fid = str(field.get("id") or "")
    s3 = _s3(deal)
    building = str(grok.get("building") or s3.get("structure") or "")
    if fid == "nearest_station":
        pop = str(grok.get("population_table") or "").strip()
        if not pop:
            return None
        # ｜以降の評価コメントは書かない
        pop = pop.split("｜")[0].split("|")[0].strip()
        pop = pop.split("·")[0].strip() if "·" in pop else pop
        return pop or None
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
        # 運営フォーム用デフォルト（estate）
        default_email = str(field.get("default_email") or "").strip()
        if fid == "email" and default_email:
            return default_email
        return None
    if src == "deal.title":
        return _suggest_folder_name(deal) or None
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
        # はい／いいえのみ（source メモは書かない）
        src_val = str(deal.get("source") or "").lower()
        if any(x in src_val for x in ("kamiooya", "神大家", "westudy", "紹介")):
            return "はい"
        return "いいえ"
    if src == "grok.land100":
        # 記載例レベル（長文の評価メモは書かない）
        ratio = grok.get("land100_ratio") or _sj(deal).get("land100_ratio")
        appraisal = grok.get("land_appraisal_man")
        lines: list[str] = []
        if ratio:
            lines.append(f"土地値 約{ratio}")
        elif grok.get("land100"):
            lines.append(str(grok["land100"]))
        if appraisal:
            lines.append(f"評価概算 約{appraisal}万円")
        return "\n".join(lines) if lines else None
    if src == "grok.hazard_eval":
        parts: list[str] = []
        if grok.get("hazard_landslide"):
            parts.append(f"土砂:{grok['hazard_landslide']}")
        if grok.get("hazard_flood"):
            parts.append(f"洪水:{grok['hazard_flood']}")
        if grok.get("hazard_eval") and not parts:
            parts.append(str(grok["hazard_eval"]))
        return "\n".join(parts) if parts else None
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
    sb: Any | None = None,
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
        f"📎 運営相談フォーム下書き — {_strip_grok_prefix(str(deal.get('title') or ''))[:60]}",
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
            # drive_folder の注釈を落とす
            if fid == "drive_folder" and isinstance(val, str):
                val = re.sub(r"\s*（フォルダ名＝物件名と一致させる）\s*$", "", val).strip()
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
                val = _load_own_funds(sb=sb)
                src_tag = "zaim_loan"
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
        sb=sb,
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
