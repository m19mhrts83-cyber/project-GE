#!/usr/bin/env python3
"""神大家運営相談フォーム（1906a1a5）へ下書きを転記（入力のみ・送信しない）。

  cd ~/git-repos && set -a && source .env.jarvis_private && set +a
  ~/selenium_env/venv/bin/python scripts/jarvis_kurashift_re_ops_form_fill.py \\
    --deal-id <uuid> --apply --headed

確認／送信ボタンは押さない（jarvis-outbound-confirm）。
ブラウザを残して松野が最終確認→送信する。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
FORM_URL_DEFAULT = "https://form.os7.biz/f/1906a1a5/"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def sb_client() -> Any:
    url = os.environ.get("JARVIS_SUPABASE_URL")
    key = os.environ.get("JARVIS_SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        raise SystemExit("JARVIS_SUPABASE_URL / JARVIS_SUPABASE_SERVICE_ROLE_KEY が必要です")
    from supabase import create_client

    return create_client(url, key)


def _sj(deal: dict[str, Any]) -> dict[str, Any]:
    sj = deal.get("summary_json")
    return sj if isinstance(sj, dict) else {}


def load_filled(deal: dict[str, Any]) -> tuple[list[dict[str, str]], str]:
    draft = _sj(deal).get("ops_form_draft")
    if not isinstance(draft, dict):
        raise SystemExit("ops_form_draft がありません。先に form draft --apply を実行してください")
    form_url = str(draft.get("form_url") or FORM_URL_DEFAULT)
    filled = draft.get("filled")
    out: list[dict[str, str]] = []
    if isinstance(filled, list) and filled:
        for f in filled:
            if not isinstance(f, dict):
                continue
            label = str(f.get("label") or f.get("id") or "").strip()
            value = str(f.get("value") or "").strip()
            if label and value:
                out.append(
                    {
                        "id": str(f.get("id") or ""),
                        "label": label,
                        "value": value,
                    }
                )
    if not out and draft.get("markdown"):
        for line in str(draft["markdown"]).splitlines():
            m = re.match(
                r"^\s*·\s*(?:\[[^\]]+\]\s*)?(.+?):\s*(.*)$",
                line,
            )
            if m:
                out.append({"id": "", "label": m.group(1).strip(), "value": m.group(2).strip()})
    if not out:
        raise SystemExit("転記する filled 項目が空です")
    return out, form_url


def _split_name(full: str) -> tuple[str, str]:
    s = full.strip()
    if not s:
        return "", ""
    if " " in s or "　" in s:
        parts = re.split(r"[\s　]+", s, maxsplit=1)
        return parts[0], parts[1] if len(parts) > 1 else ""
    if len(s) >= 2:
        return s[0], s[1:]
    return s, ""


def fill_form(
    *,
    form_url: str,
    filled: list[dict[str, str]],
    headed: bool,
    keep_open_sec: int,
) -> dict[str, Any]:
    from playwright.sync_api import sync_playwright

    ok = 0
    failed: list[str] = []
    notes: list[str] = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not headed)
        context = browser.new_context(locale="ja-JP")
        page = context.new_page()
        page.goto(form_url, wait_until="domcontentloaded", timeout=90000)
        page.wait_for_timeout(1500)

        # name special-case: 姓・名
        name_item = next((x for x in filled if x.get("id") == "name"), None)
        if name_item:
            family, given = _split_name(name_item["value"])
            if _try_fill_by_labels(page, ["姓", "（姓）"], family):
                ok += 1
            else:
                failed.append("姓名/姓")
            if given and _try_fill_by_labels(page, ["名", "（名）"], given):
                ok += 1
            else:
                if given:
                    failed.append("姓名/名")

        for item in filled:
            fid = item.get("id") or ""
            if fid == "name":
                continue
            label = item["label"]
            value = item["value"]
            # shorten label for matching (form labels are long)
            needles = _label_needles(label, fid)
            if _try_fill_by_labels(page, needles, value):
                ok += 1
            else:
                failed.append(label[:40])

        # Never click 確認 / 送信
        notes.append("確認・送信ボタンは押していません")
        if keep_open_sec > 0 and headed:
            notes.append(f"ブラウザを{keep_open_sec}秒維持（最終確認用）")
            page.wait_for_timeout(keep_open_sec * 1000)
        else:
            page.wait_for_timeout(2000)

        if headed and keep_open_sec <= 0:
            # leave open briefly then close; worker usually uses keep_open
            pass
        browser.close()

    status = "filled_pending_submit" if ok > 0 else "failed"
    if failed and ok > 0:
        status = "partial_pending_submit"
        notes.append(f"未入力: {', '.join(failed[:8])}" + ("…" if len(failed) > 8 else ""))
    elif failed and ok == 0:
        notes.append(f"未入力: {', '.join(failed[:8])}")

    return {
        "status": status,
        "filled_count": ok,
        "failed_count": len(failed),
        "failed": failed,
        "note": " / ".join(notes),
    }


def _label_needles(label: str, fid: str) -> list[str]:
    needles = [label]
    # first chunk before （ or 必須
    short = re.split(r"[（(【※]", label)[0].strip()
    if short and short not in needles:
        needles.append(short)
    # common form prefixes
    mapping = {
        "email": ["メールアドレス"],
        "planning_aligned": ["プランニング"],
        "urgency": ["至急度"],
        "kamiooya_intro": ["神大家の紹介物件"],
        "drive_folder": ["資料格納場所"],
        "property_name": ["物件名"],
        "self_funds": ["自己資金"],
        "purchase_purpose": ["購入目的"],
        "list_price": ["販売価格"],
        "offer_price": ["買付予定価格"],
        "land_value": ["土地価値"],
        "loan_terms": ["融資を使う場合", "融資依頼先"],
        "nearest_station": ["最寄駅"],
        "building_age": ["築年数"],
        "structure_rooms": ["構造、部屋数", "構造"],
        "annual_rent": ["想定年間家賃"],
        "gross_yield": ["表面利回り"],
        "repair_exterior": ["想定修繕費(外装)", "外装"],
        "repair_interior": ["想定修繕費(内装)", "内装"],
        "repair_total_yield": ["修繕費総額", "修繕後利回り"],
        "monthly_cf": ["修繕後の月CF", "月CF"],
        "occupancy": ["入居状況"],
        "building_residual": ["建物の残価値"],
        "land_sqm": ["土地平米"],
        "building_sqm": ["建物平米"],
        "features_hazard": ["他の特徴", "ハザード"],
        "gas": ["ガス状況", "ガス"],
        "parking": ["駐車場"],
        "transaction_type": ["取引形態"],
        "viewing_done": ["内見"],
        "questions_for_instructor": ["講師に確認したいこと"],
    }
    for n in mapping.get(fid, []):
        if n not in needles:
            needles.append(n)
    return needles


def _try_fill_by_labels(page: Any, needles: list[str], value: str) -> bool:
    if not value:
        return False
    # 1) getByLabel
    for n in needles:
        try:
            loc = page.get_by_label(re.compile(re.escape(n[:20])), exact=False)
            if loc.count() > 0:
                target = loc.first
                tag = (target.evaluate("el => el.tagName") or "").lower()
                if tag in ("input", "textarea", "select"):
                    target.fill(value)
                    return True
        except Exception:
            pass

    # 2) DOM walk: find text containing needle, then nearest input/textarea
    for n in needles:
        try:
            found = page.evaluate(
                """([needle, val]) => {
                  const norm = (s) => (s || '').replace(/\\s+/g, '');
                  const n = norm(needle);
                  const all = Array.from(document.querySelectorAll('label, th, td, div, span, p, dt'));
                  for (const el of all) {
                    const t = norm(el.textContent || '');
                    if (!t || t.length > 200) continue;
                    if (!t.includes(n.slice(0, Math.min(12, n.length)))) continue;
                    let input = el.querySelector('input, textarea, select');
                    if (!input) {
                      const row = el.closest('tr, .field, .form-group, li, dl') || el.parentElement;
                      if (row) input = row.querySelector('input:not([type=hidden]):not([type=submit]):not([type=button]), textarea, select');
                    }
                    if (!input) {
                      let sib = el.nextElementSibling;
                      for (let i = 0; i < 3 && sib && !input; i++, sib = sib.nextElementSibling) {
                        input = sib.querySelector?.('input:not([type=hidden]), textarea, select') ||
                          ((sib.matches?.('input,textarea,select')) ? sib : null);
                      }
                    }
                    if (input && input.type !== 'checkbox' && input.type !== 'radio') {
                      input.focus();
                      input.value = val;
                      input.dispatchEvent(new Event('input', { bubbles: true }));
                      input.dispatchEvent(new Event('change', { bubbles: true }));
                      return true;
                    }
                  }
                  return false;
                }""",
                [n, value],
            )
            if found:
                return True
        except Exception:
            continue
    return False


def persist_result(sb: Any, deal_id: str, result: dict[str, Any]) -> None:
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
    sj = dict(sj)
    sj["ops_form_fill"] = {
        "at": now_iso(),
        "status": result.get("status"),
        "filled_count": result.get("filled_count"),
        "failed_count": result.get("failed_count"),
        "failed": result.get("failed"),
        "note": result.get("note"),
    }
    sb.table("kurashift_re_deals").update(
        {"summary_json": sj, "updated_at": now_iso()}
    ).eq("id", deal_id).execute()


def main() -> int:
    ap = argparse.ArgumentParser(description="運営相談フォーム転記（送信なし）")
    ap.add_argument("--deal-id", required=True)
    ap.add_argument("--apply", action="store_true", help="ops_form_fill を summary_json に保存")
    ap.add_argument("--headed", action="store_true", help="ブラウザ表示（確認用）")
    ap.add_argument(
        "--keep-open-sec",
        type=int,
        default=120,
        help="headed 時にブラウザを維持する秒数（最終確認用。既定120）",
    )
    ap.add_argument("--dry-run", action="store_true", help="入力せず項目数だけ表示")
    args = ap.parse_args()

    sys.path.insert(0, str(REPO / "scripts"))
    from jarvis_kurashift_re_inquiry import get_deal  # noqa: E402

    sb = sb_client()
    deal = get_deal(sb, args.deal_id)
    filled, form_url = load_filled(deal)
    print(f"# deal={args.deal_id[:8]}… fields={len(filled)} url={form_url}")
    for f in filled[:5]:
        print(f"  · {f['label'][:40]}: {f['value'][:60]}")
    if len(filled) > 5:
        print(f"  … +{len(filled) - 5}")

    if args.dry_run:
        print("# dry-run: skip browser")
        return 0

    result = fill_form(
        form_url=form_url,
        filled=filled,
        headed=args.headed,
        keep_open_sec=args.keep_open_sec if args.headed else 0,
    )
    print(
        f"# result status={result['status']} filled={result['filled_count']} "
        f"failed={result['failed_count']} note={result.get('note')}"
    )
    if args.apply:
        persist_result(sb, args.deal_id, result)
        print(f"# ops_form_fill saved to deal {args.deal_id[:8]}…")

    print("KURASHIFT_RESULT:" + json.dumps(result, ensure_ascii=False))
    return 0 if result.get("filled_count", 0) > 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
