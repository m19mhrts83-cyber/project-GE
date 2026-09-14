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
    """姓名を姓・名に分割。スペース無し日本語は1文字切りしない。

    優先: PERSONAL_NAME_FAMILY / PERSONAL_NAME_GIVEN → 空白分割
    → 既知の2文字姓（松野など）→ 残りを名。
    """
    family_env = (os.environ.get("PERSONAL_NAME_FAMILY") or "").strip()
    given_env = (os.environ.get("PERSONAL_NAME_GIVEN") or "").strip()
    if family_env and given_env:
        return family_env, given_env

    s = full.strip()
    if not s:
        return "", ""
    if " " in s or "　" in s:
        parts = re.split(r"[\s　]+", s, maxsplit=1)
        return parts[0], parts[1] if len(parts) > 1 else ""

    # 2文字姓のヒューリスティック（チャット固定ではなく env 優先）
    two_char = ("松野", "佐藤", "鈴木", "高橋", "田中", "伊藤", "渡辺", "山本", "中村", "小林")
    for sur in two_char:
        if s.startswith(sur) and len(s) > len(sur):
            return sur, s[len(sur) :]
    # 3文字姓の簡易（例: 佐々木）
    if len(s) >= 4 and s[1] == "々":
        return s[:3], s[3:]
    # 不明時は後半を名とみなす（2文字姓想定）
    if len(s) >= 3:
        return s[:2], s[2:]
    return s, ""


def fill_form(
    *,
    form_url: str,
    filled: list[dict[str, str]],
    headed: bool,
    keep_open_sec: int,
) -> dict[str, Any]:
    """入力して結果を返す。leave-open（keep_open_sec<0）時はブラウザを維持したまま戻る前に
    呼び出し側が RESULT を書き出せるよう、closer は返さず main 側で sleep する。
    実装: leave-open のときは結果 dict に _browser_keep を載せず、main が再起動せず
    fill 完了直後に RESULT を出してから sleep するよう fill_and_maybe_keep を使う。
    """
    return fill_and_maybe_keep(
        form_url=form_url,
        filled=filled,
        headed=headed,
        keep_open_sec=keep_open_sec,
        block_keep=False,
    )


def fill_and_maybe_keep(
    *,
    form_url: str,
    filled: list[dict[str, str]],
    headed: bool,
    keep_open_sec: int,
    block_keep: bool,
) -> dict[str, Any]:
    from playwright.sync_api import sync_playwright

    ok = 0
    failed: list[str] = []
    notes: list[str] = []
    leave_open = keep_open_sec < 0 and headed

    pw = sync_playwright().start()
    browser = pw.chromium.launch(headless=not headed)
    try:
        context = browser.new_context(locale="ja-JP")
        page = context.new_page()
        page.goto(form_url, wait_until="domcontentloaded", timeout=90000)
        page.wait_for_timeout(1500)

        name_item = next((x for x in filled if x.get("id") == "name"), None)
        if name_item:
            family, given = _split_name(name_item["value"])
            # os7 フォームは id=seimei1（姓）/ seimei2（名）が正
            filled_family = False
            filled_given = False
            try:
                loc1 = page.locator("#seimei1")
                if loc1.count() > 0 and family:
                    loc1.first.fill(family)
                    filled_family = True
                    ok += 1
            except Exception:
                pass
            try:
                loc2 = page.locator("#seimei2")
                if loc2.count() > 0 and given:
                    loc2.first.fill(given)
                    filled_given = True
                    ok += 1
            except Exception:
                pass
            if not filled_family:
                if _try_fill_by_labels(page, ["姓", "（姓）"], family):
                    ok += 1
                else:
                    failed.append("姓名/姓")
            if given and not filled_given:
                if _try_fill_by_labels(page, ["名", "（名）"], given):
                    ok += 1
                else:
                    failed.append("姓名/名")

        for item in filled:
            fid = item.get("id") or ""
            if fid == "name":
                continue
            label = item["label"]
            value = item["value"]
            needles = _label_needles(label, fid)
            if _try_fill_by_labels(page, needles, value):
                ok += 1
            else:
                failed.append(label[:40])

        notes.append("確認・送信ボタンは押していません")
        if leave_open:
            notes.append("ブラウザは閉じず残しています（検証用・手動で閉じてください）")
        elif keep_open_sec > 0 and headed:
            notes.append(f"ブラウザを{keep_open_sec}秒維持（最終確認用）")
            page.wait_for_timeout(keep_open_sec * 1000)
        else:
            page.wait_for_timeout(2000)

        status = "filled_pending_submit" if ok > 0 else "failed"
        if failed and ok > 0:
            status = "partial_pending_submit"
            notes.append(
                f"未入力: {', '.join(failed[:8])}" + ("…" if len(failed) > 8 else "")
            )
        elif failed and ok == 0:
            notes.append(f"未入力: {', '.join(failed[:8])}")

        result = {
            "status": status,
            "filled_count": ok,
            "failed_count": len(failed),
            "failed": failed,
            "note": " / ".join(notes),
            "_leave_open": leave_open,
        }

        if leave_open and block_keep:
            # RESULT 出力後に main から呼ぶ想定。ここでは閉じない。
            try:
                while True:
                    time.sleep(3600)
            except KeyboardInterrupt:
                pass
        return result
    finally:
        if not leave_open:
            try:
                browser.close()
            except Exception:
                pass
            try:
                pw.stop()
            except Exception:
                pass
        else:
            # leave-open: browser/pw はプロセス生存中に維持。グローバルに逃がす
            global _KEEP_BROWSER, _KEEP_PW
            _KEEP_BROWSER = browser
            _KEEP_PW = pw


_KEEP_BROWSER = None
_KEEP_PW = None


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
        default=-1,
        help="headed 時: >0=秒数維持, -1=閉じない（検証用既定）, 0=すぐ閉じる",
    )
    ap.add_argument(
        "--leave-open",
        action="store_true",
        help="ブラウザを閉じない（--keep-open-sec -1 と同義）",
    )
    ap.add_argument("--dry-run", action="store_true", help="入力せず項目数だけ表示")
    args = ap.parse_args()
    if args.leave_open:
        args.keep_open_sec = -1

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

    result = fill_and_maybe_keep(
        form_url=form_url,
        filled=filled,
        headed=args.headed,
        keep_open_sec=args.keep_open_sec if args.headed else 0,
        block_keep=False,
    )
    # 内部フラグはログに出さない
    leave_open = bool(result.pop("_leave_open", False))
    print(
        f"# result status={result['status']} filled={result['filled_count']} "
        f"failed={result['failed_count']} note={result.get('note')}"
    )
    if args.apply:
        persist_result(sb, args.deal_id, result)
        print(f"# ops_form_fill saved to deal {args.deal_id[:8]}…")

    print("KURASHIFT_RESULT:" + json.dumps(result, ensure_ascii=False))
    sys.stdout.flush()

    if leave_open and args.headed:
        print("# leave-open: keeping browser (Ctrl+C or close window to end)")
        sys.stdout.flush()
        try:
            while True:
                time.sleep(3600)
        except KeyboardInterrupt:
            print("# leave-open interrupted")
        finally:
            try:
                if _KEEP_BROWSER is not None:
                    _KEEP_BROWSER.close()
            except Exception:
                pass
            try:
                if _KEEP_PW is not None:
                    _KEEP_PW.stop()
            except Exception:
                pass

    return 0 if result.get("filled_count", 0) > 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
