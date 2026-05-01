#!/usr/bin/env python3
"""
ライフプラン自動化 Step4:
滋賀銀行マイページにログインし、「明細の確認」一覧から
「ご融資資金返済予定明細表」のPDFを保存して金額を抽出する。

一覧ではダウンロード未完了（「済」でない行）を優先し、
同一条件なら発行日が最も新しい行のPDFを取得する。
すべて「済」のときは発行日最新行を再ダウンロードする。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin, urlparse, urlunparse

import pdfplumber
from playwright.sync_api import Download
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright


SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_ENV_PATH = SCRIPT_DIR / ".env.lifeplan"
DEFAULT_DEBUG_DIR = SCRIPT_DIR / "debug"


@dataclass
class ShigaLoanProduct:
    """1通の返済予定表PDFに対応（セゾンF / オリコ 等）。"""

    kind: str
    amount_jpy: int
    amount_detail: str
    pdf_path: str


@dataclass
class ShigaLoanResult:
    """amount_jpy はセゾンF・オリコ等の合計。products に内訳あり。"""

    amount_jpy: int
    amount_text: str
    source_url: str
    parser_mode: str
    pdf_path: str
    products: list[ShigaLoanProduct]


def _load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'\"")
        if key and value and key not in os.environ:
            os.environ[key] = value


def _normalize_text(text: str) -> str:
    if not text:
        return ""
    trans = str.maketrans(
        "０１２３４５６７８９＋－，．",
        "0123456789+-,.",
    )
    return text.translate(trans).replace("\u3000", " ")


def _parse_first_jpy(text: str) -> tuple[int | None, str]:
    normalized = _normalize_text(text)
    m = re.search(r"([+-]?\d[\d,]{0,})(?:\s*円)?", normalized)
    if not m:
        return None, ""
    raw = m.group(1).replace(",", "")
    try:
        return int(raw), m.group(0).strip()
    except ValueError:
        return None, ""


def _extract_jpy_near_label(text: str, label: str) -> tuple[int | None, str]:
    body = _normalize_text(text)
    if not body or not label:
        return None, ""
    p1 = rf"{re.escape(label)}[^\n\r]{{0,60}}?([+-]?\d[\d,]{{0,}}(?:\s*円)?)"
    m = re.search(p1, body)
    if m:
        return _parse_first_jpy(m.group(1))
    p2 = rf"([+-]?\d[\d,]{{0,}}(?:\s*円)?)[^\n\r]{{0,30}}?{re.escape(label)}"
    m = re.search(p2, body)
    if m:
        return _parse_first_jpy(m.group(1))
    return None, ""


def _resolve_otp_code(otp_code_from_env: str, otp_code_override: str | None) -> str:
    code = (otp_code_override or otp_code_from_env or "").strip()
    if code:
        return code
    if not sys.stdin.isatty():
        return ""
    return input("滋賀銀行ワンタイムパスワードを入力してください: ").strip()


def _wait_page_ready(page, timeout_ms: int) -> None:
    page.wait_for_load_state("domcontentloaded", timeout=timeout_ms)
    try:
        page.wait_for_load_state("networkidle", timeout=min(timeout_ms, 10000))
    except Exception:
        pass


def _click_by_selector_or_text(page, *, selector: str, text: str, timeout_ms: int) -> bool:
    if selector:
        loc = page.locator(selector).first
        if loc.count() > 0 and loc.is_visible():
            loc.click(timeout=timeout_ms)
            return True
    if text:
        loc = page.locator(f"button:has-text('{text}'), a:has-text('{text}')").first
        if loc.count() > 0 and loc.is_visible():
            loc.click(timeout=timeout_ms)
            return True
    return False


def _frames_ordered(page):
    mf = page.main_frame
    return [mf] + [f for f in page.frames if f != mf]


def _try_click_in_frame(fr, *, selector: str, text: str, timeout_ms: int) -> bool:
    if selector:
        try:
            loc = fr.locator(selector).first
            if loc.count() > 0:
                loc.click(timeout=timeout_ms)
                return True
        except Exception:
            pass
    if text:
        for q in (
            f"a:has-text('{text}')",
            f"button:has-text('{text}')",
            f"[role='button']:has-text('{text}')",
            f"text={text}",
        ):
            try:
                loc = fr.locator(q).first
                if loc.count() > 0:
                    loc.click(timeout=timeout_ms)
                    return True
            except Exception:
                continue
    return False


def _click_by_selector_or_text_any_frame(page, *, selector: str, text: str, timeout_ms: int) -> bool:
    for fr in _frames_ordered(page):
        if _try_click_in_frame(fr, selector=selector, text=text, timeout_ms=timeout_ms):
            return True
    return False


def _meisai_url_from_login(login_url: str) -> str:
    """お取引書類Web確認サービス「明細の確認」画面のURL（ログインURLと同一オリジン）。"""
    p = urlparse(login_url.strip())
    if not p.scheme or not p.netloc:
        raise RuntimeError("SHIGA_LOAN_LOGIN_URL が不正です。")
    path = "/shigagin/mypage/bapPublishedBillAppSearch"
    return urlunparse((p.scheme, p.netloc, path, "", "", ""))


def _normalize_for_match(text: str) -> str:
    return (text or "").replace(" ", "").replace("\u3000", "").replace("\n", "")


def _parse_issue_date_from_text(text: str) -> tuple[int, int, int] | None:
    """発行日セルや行テキストから YYYY/MM/DD / YYYY.MM.DD を拾う。"""
    s = _normalize_text(text or "")
    for pat in (
        r"(\d{4})[/.年](\d{1,2})[/.月](\d{1,2})",
        r"(\d{4})\.(\d{2})\.(\d{2})",
    ):
        m = re.search(pat, s)
        if m:
            y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
            if 1990 <= y <= 2100 and 1 <= mo <= 12 and 1 <= d <= 31:
                return y, mo, d
    return None


def _row_marked_zumi(row_text: str) -> bool:
    """ダウンロード済み（画面上で「済」と表示）なら True。"""
    return "済" in (row_text or "")


def _find_meisai_table_rows(page):
    """楽楽明細の一覧テーブル行を返す（iframe 内も探索）。"""
    for fr in _frames_ordered(page):
        for sel in ("table tbody tr", "table tr", '[role="row"]'):
            rows = fr.locator(sel)
            try:
                n = rows.count()
            except Exception:
                continue
            if n >= 2:
                return fr, rows
            if n == 1:
                return fr, rows
    return None, None


def _find_pdf_anchor_in_row(row) -> object | None:
    """行内の PDF ダウンロード用 a を特定する。"""
    try:
        n = row.locator("a").count()
    except Exception:
        return None
    for j in range(n):
        a = row.locator("a").nth(j)
        try:
            href = (a.get_attribute("href") or "").strip()
            inner = (a.inner_text() or "").strip()
        except Exception:
            continue
        h = href.lower()
        inn = inner.lower()
        if ".pdf" in h or ".pdf" in inn or h.endswith("pdf") or inn.endswith(".pdf"):
            return a
    return None


def _pick_best_schedule_row_link(
    rows_locator,
    *,
    doc_title_contains: str,
) -> tuple | None:
    """
    ご融資返済予定明細の行から、
    優先: 「済」でない行のうち発行日が最新
    フォールバック: すべて「済」なら発行日が最新の行
    返値: (Locator 行内の PDF 用 a, issue_date, used_non_zumi_pool) または None
    """
    doc_key = _normalize_for_match(doc_title_contains)
    collected: list[tuple[tuple[int, int, int], str, bool, object]] = []
    try:
        n = rows_locator.count()
    except Exception:
        return None
    for i in range(n):
        row = rows_locator.nth(i)
        try:
            text = row.inner_text(timeout=5000)
        except Exception:
            continue
        norm = _normalize_for_match(text)
        if doc_key not in norm:
            continue
        issue = _parse_issue_date_from_text(text)
        if issue is None:
            continue
        zumi = _row_marked_zumi(text)
        link = _find_pdf_anchor_in_row(row)
        if link is None:
            continue
        href = ""
        try:
            href = (link.get_attribute("href") or "").strip()
        except Exception:
            pass
        collected.append((issue, href, zumi, link))

    if not collected:
        return None

    def sort_key(item: tuple) -> tuple:
        issue, href, _zumi, _link = item
        return (issue[0], issue[1], issue[2], href)

    non_zumi = [c for c in collected if not c[2]]
    pool = non_zumi if non_zumi else collected
    pool_sorted = sorted(pool, key=sort_key, reverse=True)
    best_issue, best_href, best_zumi, best_link = pool_sorted[0]
    used_non_zumi = len(non_zumi) > 0
    return (best_link, best_issue, used_non_zumi)


def _collect_unique_schedule_pdf_links_ordered(
    rows_locator,
    *,
    doc_title_contains: str,
) -> list:
    """
    ご融資返済予定明細の行から、href ごとにユニークな PDF リンクを列挙する。
    優先: 未「済」→発行日が新しい順。同一 href はより優先度の高い行で代表。
    """
    doc_key = _normalize_for_match(doc_title_contains)
    rows_data: list[tuple[tuple[int, int, int], str, bool, object]] = []
    try:
        n = rows_locator.count()
    except Exception:
        return []
    for i in range(n):
        row = rows_locator.nth(i)
        try:
            text = row.inner_text(timeout=5000)
        except Exception:
            continue
        norm = _normalize_for_match(text)
        if doc_key not in norm:
            continue
        issue = _parse_issue_date_from_text(text)
        if issue is None:
            continue
        zumi = _row_marked_zumi(text)
        link = _find_pdf_anchor_in_row(row)
        if link is None:
            continue
        href = ""
        try:
            href = (link.get_attribute("href") or "").strip()
        except Exception:
            pass
        if not href:
            continue
        rows_data.append((issue, href, zumi, link))

    # href が同一でも、セゾン/オリコなど別商品が紐づくことがあるため kind もキーに含める
    best: dict[str, tuple[tuple[int, int, int], bool, object]] = {}
    for issue, href, zumi, link in rows_data:
        kind = ""
        try:
            # row の inner_text を再利用して kind 推定（毎回 PDF を開かずに内訳を落とさない）
            kind = _extract_loan_kind_from_row_text(
                link.locator("xpath=ancestor-or-self::tr[1]").inner_text(timeout=2000)
            )
        except Exception:
            kind = ""
        key = f"{href}|{kind}" if kind else href
        if key not in best:
            best[key] = (issue, zumi, link)
            continue
        o_issue, o_zumi, o_link = best[key]
        if o_zumi and not zumi:
            best[key] = (issue, zumi, link)
        elif o_zumi == zumi and issue > o_issue:
            best[key] = (issue, zumi, link)

    entries = list(best.values())
    non_z = sorted([e for e in entries if not e[1]], key=lambda e: e[0], reverse=True)
    z_only = sorted([e for e in entries if e[1]], key=lambda e: e[0], reverse=True)
    return [e[2] for e in non_z + z_only]


def _collect_all_pdf_links_ordered(rows_locator) -> list:
    """明細一覧の行から PDF リンクを広く列挙（doc_title_contains フィルタなし）。"""
    try:
        n = rows_locator.count()
    except Exception:
        return []
    rows_data: list[tuple[tuple[int, int, int], bool, object]] = []
    for i in range(n):
        row = rows_locator.nth(i)
        try:
            text = row.inner_text(timeout=5000)
        except Exception:
            continue
        issue = _parse_issue_date_from_text(text)
        if issue is None:
            continue
        zumi = _row_marked_zumi(text)
        link = _find_pdf_anchor_in_row(row)
        if link is None:
            continue
        rows_data.append((issue, zumi, link))
    # 未「済」→発行日降順→「済」降順
    non_z = sorted([e for e in rows_data if not e[1]], key=lambda e: e[0], reverse=True)
    z_only = sorted([e for e in rows_data if e[1]], key=lambda e: e[0], reverse=True)
    return [e[2] for e in non_z + z_only]


def _download_schedule_pdfs_from_meisai_table(
    page,
    output_dir: Path,
    *,
    doc_title_contains: str,
    timeout_ms: int,
) -> list[Path]:
    """明細一覧から返済予定表PDFを複数保存し、保存パスのリストを返す。"""
    try:
        page.wait_for_timeout(2000)
    except Exception:
        pass
    per_dl = min(25000, max(10000, timeout_ms // 4 or 15000))
    saved: list[Path] = []
    for attempt in range(25):
        fr, rows = _find_meisai_table_rows(page)
        if rows is None or rows.count() == 0:
            try:
                page.wait_for_timeout(400)
            except Exception:
                pass
            continue
        link_locs = _collect_unique_schedule_pdf_links_ordered(
            rows, doc_title_contains=doc_title_contains
        )
        if not link_locs:
            try:
                page.wait_for_timeout(400)
            except Exception:
                pass
            continue
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        for idx, link_loc in enumerate(link_locs):
            out = output_dir / f"滋賀銀行_ご融資資金返済予定明細表_{ts}_{idx:02d}.pdf"
            try:
                link_loc.scroll_into_view_if_needed(timeout=min(8000, per_dl))
            except Exception:
                pass
            try:
                with page.expect_download(timeout=per_dl) as info:
                    link_loc.click(timeout=min(12000, per_dl))
                dl = info.value
                dl.save_as(str(out))
                if out.exists():
                    saved.append(out)
            except Exception:
                continue
        if saved:
            return saved
        try:
            page.wait_for_timeout(400)
        except Exception:
            pass
    return []


def _download_all_pdfs_from_meisai_table(page, output_dir: Path, *, timeout_ms: int) -> list[Path]:
    """doc_title_contains で拾えなかった場合の保険: 一覧のPDFリンクを広めに落とす。"""
    try:
        page.wait_for_timeout(1500)
    except Exception:
        pass
    per_dl = min(25000, max(10000, timeout_ms // 4 or 15000))
    saved: list[Path] = []
    fr, rows = _find_meisai_table_rows(page)
    if rows is None or rows.count() == 0:
        return []
    link_locs = _collect_all_pdf_links_ordered(rows)
    if not link_locs:
        return []
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    for idx, link_loc in enumerate(link_locs[:6]):  # 多すぎるDLを避ける
        out = output_dir / f"滋賀銀行_明細PDF_{ts}_{idx:02d}.pdf"
        try:
            link_loc.scroll_into_view_if_needed(timeout=min(8000, per_dl))
        except Exception:
            pass
        try:
            with page.expect_download(timeout=per_dl) as info:
                link_loc.click(timeout=min(12000, per_dl))
            dl = info.value
            dl.save_as(str(out))
            if out.exists():
                saved.append(out)
        except Exception:
            continue
    return saved


def _download_schedule_pdf_from_meisai_table(
    page,
    *,
    doc_title_contains: str,
    timeout_ms: int,
) -> Download | None:
    """単一PDF取得（フォールバック用）。"""
    try:
        page.wait_for_timeout(2000)
    except Exception:
        pass
    deadline = min(timeout_ms, 25000)
    for _ in range(20):
        fr, rows = _find_meisai_table_rows(page)
        if rows is not None and rows.count() > 0:
            picked = _pick_best_schedule_row_link(rows, doc_title_contains=doc_title_contains)
            if picked is not None:
                link_loc, _issue, _nz = picked
                try:
                    link_loc.scroll_into_view_if_needed(timeout=min(10000, deadline))
                except Exception:
                    pass
                try:
                    with page.expect_download(timeout=deadline) as info:
                        link_loc.click(timeout=min(15000, deadline))
                    return info.value
                except Exception:
                    pass
        try:
            page.wait_for_timeout(400)
        except Exception:
            pass
    return None


def _pdf_download_text_candidates(primary: str) -> list[str]:
    out: list[str] = []
    if primary:
        out.append(primary)
    for t in (
        "ご融資資金返済予定明細表",
        "返済予定明細表",
        "ご融資資金返済予定",
        "返済予定",
        "PDFを表示",
        "PDF出力",
        "PDF",
    ):
        if t not in out:
            out.append(t)
    return out


def _download_pdf_any_frame(
    page,
    *,
    selector: str,
    text_candidates: list[str],
    timeout_ms: int,
) -> Download | None:
    for fr in _frames_ordered(page):
        if selector:
            try:
                loc = fr.locator(selector).first
                if loc.count() > 0:
                    with page.expect_download(timeout=timeout_ms) as info:
                        loc.click(timeout=timeout_ms)
                    return info.value
            except Exception:
                pass
        for text in text_candidates:
            for q in (
                f"a:has-text('{text}')",
                f"button:has-text('{text}')",
                f"span:has-text('{text}')",
                f"text={text}",
            ):
                try:
                    loc = fr.locator(q).first
                    if loc.count() == 0:
                        continue
                    with page.expect_download(timeout=timeout_ms) as info:
                        loc.click(timeout=timeout_ms)
                    return info.value
                except Exception:
                    continue
    return None


def _download_by_link_fallback_any_frame(page, timeout_ms: int) -> bytes | None:
    for fr in _frames_ordered(page):
        loc = fr.locator("a[href*='.pdf'], a[href*='Pdf'], a[href*='pdf'], a[href*='PDF']")
        try:
            if loc.count() == 0:
                continue
            href = (loc.first.get_attribute("href") or "").strip()
            if not href:
                continue
            url = urljoin(page.url, href)
            response = page.context.request.get(url, timeout=timeout_ms)
            if response.ok:
                return response.body()
        except Exception:
            continue
    return None


def _resolve_output_dir(raw: str, env_file: Path) -> Path:
    value = (raw or "").strip()
    if not value:
        raise RuntimeError(
            "SHIGA_LOAN_PDF_DIR が未設定です。PDF保存先フォルダを .env.lifeplan に設定してください。"
        )
    p = Path(value).expanduser()
    if not p.is_absolute():
        p = (env_file.expanduser().resolve().parent / p).resolve()
    p.mkdir(parents=True, exist_ok=True)
    return p


def _build_pdf_path(dest_dir: Path, *, index: int | None = None) -> Path:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    if index is None:
        return dest_dir / f"滋賀銀行_ご融資資金返済予定明細表_{ts}.pdf"
    return dest_dir / f"滋賀銀行_ご融資資金返済予定明細表_{ts}_{index:02d}.pdf"


def _extract_loan_kind_from_pdf_text(full_text: str) -> str:
    """PDF 先頭付近の「ローン名称」行からセゾンF / オリコ等を判別する。"""
    m = re.search(r"ローン名称\s*([^\n\r]+)", full_text)
    line = (m.group(1) if m else "").strip()
    if not line:
        return "不明"
    if "セゾン" in line:
        return "セゾンファイナンス"
    if "オリコ" in line:
        return "オリコ"
    return line[:80]


def _extract_loan_kind_from_row_text(row_text: str) -> str:
    """一覧行のテキストからセゾン/オリコを推定（href が共通でも内訳を落とさない）。"""
    s = _normalize_text(row_text or "")
    if "セゾン" in s:
        return "セゾンファイナンス"
    if "オリコ" in s:
        return "オリコ"
    return ""


def _sort_shiga_products(products: list[ShigaLoanProduct]) -> list[ShigaLoanProduct]:
    order = {"セゾンファイナンス": 0, "オリコ": 1}
    return sorted(products, key=lambda p: (order.get(p.kind, 50), p.kind))


def _format_shiga_amount_text(products: list[ShigaLoanProduct], total: int) -> str:
    lines = []
    for p in products:
        lines.append(f"{p.kind}: {p.amount_detail}")
    lines.append(f"合計: {total:,}円")
    return "\n".join(lines)


def _extract_max_jpy_in_text(text: str) -> tuple[int | None, str]:
    vals: list[int] = []
    for m in re.finditer(r"[+-]?\d[\d,]{0,}", _normalize_text(text or "")):
        v, _ = _parse_first_jpy(m.group(0))
        if v is not None:
            vals.append(v)
    if not vals:
        return None, ""
    mx = max(vals)
    return mx, f"{mx:,}円"


def _products_from_pdf(pdf_path: Path, amount_label: str) -> list[ShigaLoanProduct]:
    """1つのPDFに複数ローン（セゾン/オリコ等）が混在するケースに対応して内訳を返す。"""
    pages_text: list[str] = []
    with pdfplumber.open(str(pdf_path)) as pdf:
        for page in pdf.pages:
            t = page.extract_text() or ""
            if t:
                pages_text.append(t)
    full_text = "\n".join(pages_text)

    # まずは従来のPDF全体抽出（単一ローン想定）
    try:
        amount_jpy, amount_detail, _mode = _extract_balance_from_pdf_smart(pdf_path, amount_label)
    except Exception:
        amount_jpy, amount_detail = 0, ""
    kind = _extract_loan_kind_from_pdf_text(full_text)
    base = ShigaLoanProduct(
        kind=kind,
        amount_jpy=int(amount_jpy),
        amount_detail=amount_detail or f"{int(amount_jpy):,}円",
        pdf_path=str(pdf_path),
    )

    # PDF内に「ローン名称」が複数あり、かつセゾン/オリコの両方が含まれる場合は分割抽出を試す
    if "ローン名称" not in full_text:
        return [base]
    has_saison = "セゾン" in full_text
    has_orico = "オリコ" in full_text
    if not (has_saison and has_orico):
        return [base]

    parts = re.split(r"ローン名称", full_text)
    found: list[ShigaLoanProduct] = []
    for seg in parts[1:]:
        seg_text = ("ローン名称" + seg).strip()
        seg_kind = _extract_loan_kind_from_pdf_text(seg_text)
        if seg_kind not in ("セゾンファイナンス", "オリコ"):
            continue
        v, detail = _extract_jpy_near_label(seg_text, amount_label)
        if v is None:
            v, detail = _extract_max_jpy_in_text(seg_text)
        if v is None:
            continue
        found.append(
            ShigaLoanProduct(
                kind=seg_kind,
                amount_jpy=int(v),
                amount_detail=detail or f"{int(v):,}円",
                pdf_path=str(pdf_path),
            )
        )
    if found:
        # 同種が複数出た場合は最大のものを採用（同一PDF内の繰越等の重複対策）
        by_kind: dict[str, ShigaLoanProduct] = {}
        for p in found:
            cur = by_kind.get(p.kind)
            if cur is None or p.amount_jpy > cur.amount_jpy:
                by_kind[p.kind] = p
        return list(by_kind.values())

    return [base]


def _parse_yyyy_mm_dd_cell(cell: str) -> tuple[int, int, int] | None:
    s = _normalize_text(cell or "").strip().replace(" ", "").replace("　", "")
    m = re.match(r"^(\d{4})\.(\d{2})\.(\d{2})$", s)
    if not m:
        return None
    return int(m.group(1)), int(m.group(2)), int(m.group(3))


def _balance_from_schedule_row_cells(cells: list[str]) -> int | None:
    """返済予定行内の数値から、ご融資残高列（通常は行内最大の金額）を推定する。"""
    vals: list[int] = []
    for c in cells:
        if not c:
            continue
        for m in re.finditer(r"[+-]?\d[\d,]{0,}", _normalize_text(c)):
            v, _ = _parse_first_jpy(m.group(0))
            if v is not None:
                vals.append(v)
    if not vals:
        return None
    return max(vals)


def _extract_latest_month_balance_from_pdf(pdf_path: Path) -> tuple[int, str, str]:
    """
    「ご融資資金返済予定明細表」形式: 約定返済日 YYYY.MM.DD ごとにご融資残高がある行のうち、
    日付が最も新しい行の残高を返す。
    """
    best_date: tuple[int, int, int] | None = None
    best_bal: int | None = None
    best_snippet = ""
    carryover: int | None = None

    with pdfplumber.open(str(pdf_path)) as pdf:
        for page in pdf.pages:
            for table in page.extract_tables() or []:
                for row in table:
                    if not row:
                        continue
                    cells = [(_normalize_text(c).strip() if c else "") for c in row]
                    joined = "".join(cells)
                    if "繰越残高" in joined.replace(" ", "").replace("　", ""):
                        for c in cells:
                            v, _ = _parse_first_jpy(c or "")
                            if v is not None and v >= 1000:
                                carryover = v
                                break
                    dt: tuple[int, int, int] | None = None
                    for c in cells:
                        dt = _parse_yyyy_mm_dd_cell(c)
                        if dt:
                            break
                        compact = _normalize_text(c or "").replace(" ", "").replace("　", "")
                        m2 = re.match(r"^(\d+)(\d{4}\.\d{2}\.\d{2})$", compact)
                        if m2:
                            dt = _parse_yyyy_mm_dd_cell(m2.group(2))
                            if dt:
                                break
                    if not dt:
                        continue
                    bal = _balance_from_schedule_row_cells(cells)
                    if bal is None:
                        continue
                    if best_date is None or dt > best_date:
                        best_date = dt
                        best_bal = bal
                        best_snippet = " | ".join(x for x in cells if x)[:200]

            text = page.extract_text() or ""
            for line in text.splitlines():
                line_n = _normalize_text(line).strip()
                if not re.search(r"\d{4}\.\d{2}\.\d{2}", line_n):
                    continue
                parts = re.split(r"\s+", line_n)
                dt = None
                rest_start = 0
                for i, p in enumerate(parts):
                    t = _parse_yyyy_mm_dd_cell(p)
                    if t:
                        dt = t
                        rest_start = i + 1
                        break
                    mconcat = re.match(r"^(\d+)(\d{4}\.\d{2}\.\d{2})$", p.replace(" ", ""))
                    if mconcat:
                        t = _parse_yyyy_mm_dd_cell(mconcat.group(2))
                        if t:
                            dt = t
                            rest_start = i + 1
                            break
                if not dt:
                    continue
                rest_cells = parts[rest_start:]
                bal = _balance_from_schedule_row_cells(rest_cells)
                if bal is None:
                    continue
                if best_date is None or dt > best_date:
                    best_date = dt
                    best_bal = bal
                    best_snippet = line_n[:200]

    if best_date is not None and best_bal is not None:
        y, mo, d = best_date
        ds = f"{y}.{mo:02d}.{d:02d}"
        return (
            best_bal,
            f"{best_bal:,}円（約定返済日 {ds} 時点のご融資残高）",
            f"pdf:latest-month:{ds}",
        )

    if carryover is not None:
        return carryover, f"{carryover:,}円（繰越残高）", "pdf:carryover"

    raise RuntimeError("返済予定の日付行をPDFから特定できませんでした。")


def _extract_amount_from_pdf(pdf_path: Path, label: str) -> tuple[int, str, str]:
    pages_text: list[str] = []
    with pdfplumber.open(str(pdf_path)) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            if text:
                pages_text.append(text)
    full_text = "\n".join(pages_text)
    if not full_text.strip():
        raise RuntimeError("PDFからテキストを読み取れませんでした。画像PDFの可能性があります。")

    if label:
        value, amount_text = _extract_jpy_near_label(full_text, label)
        if value is not None:
            return value, amount_text or f"{value:,}円", f"pdf:label:{label}"

    all_hits = re.findall(r"([+-]?\d[\d,]{0,})(?:\s*円)?", _normalize_text(full_text))
    values: list[int] = []
    for hit in all_hits:
        raw = hit.replace(",", "").strip()
        if raw and raw.lstrip("+-").isdigit():
            values.append(int(raw))

    if not values:
        raise RuntimeError(
            "PDF内の金額候補を検出できませんでした。SHIGA_LOAN_AMOUNT_LABEL を見直してください。"
        )

    if len(values) == 1:
        v = values[0]
        return v, f"{v:,}円", "pdf:single-candidate"

    max_v = max(values)
    return max_v, f"{max_v:,}円", "pdf:max-candidate"


def _extract_balance_from_pdf_smart(pdf_path: Path, label: str) -> tuple[int, str, str]:
    """優先: 返済予定表の最新約定返済日のご融資残高。失敗時はラベル／従来ヒューリスティック。"""
    try:
        return _extract_latest_month_balance_from_pdf(pdf_path)
    except RuntimeError:
        pass
    return _extract_amount_from_pdf(pdf_path, label)


def fetch_shiga_loan_balance(
    *,
    headless: bool,
    timeout_ms: int,
    save_debug: bool,
    env_file: Path,
    otp_code_override: str | None = None,
) -> ShigaLoanResult:
    _load_env_file(env_file)

    login_url = os.environ.get("SHIGA_LOAN_LOGIN_URL", "").strip()
    if not login_url:
        raise RuntimeError("SHIGA_LOAN_LOGIN_URL が未設定です。")

    username = os.environ.get("SHIGA_LOAN_USERNAME", "").strip()
    password = os.environ.get("SHIGA_LOAN_PASSWORD", "").strip()
    # お取引書類Web確認サービス（滋賀銀行マイページ）ログイン画面の既定値
    username_selector = (
        os.environ.get("SHIGA_LOAN_USERNAME_SELECTOR", "").strip() or "#loginId"
    )
    password_selector = (
        os.environ.get("SHIGA_LOAN_PASSWORD_SELECTOR", "").strip() or "#password"
    )
    submit_selector = (
        os.environ.get("SHIGA_LOAN_SUBMIT_SELECTOR", "").strip()
        or 'button[type="submit"]:has-text("ログイン")'
    )
    otp_code_env = os.environ.get("SHIGA_LOAN_OTP_CODE", "").strip()
    otp_selector = os.environ.get("SHIGA_LOAN_OTP_SELECTOR", "").strip()
    otp_submit_selector = os.environ.get("SHIGA_LOAN_OTP_SUBMIT_SELECTOR", "").strip()
    target_url = os.environ.get("SHIGA_LOAN_TARGET_URL", "").strip()
    to_detail_selector = os.environ.get("SHIGA_LOAN_TO_DETAIL_SELECTOR", "").strip()
    doc_title_contains = (
        os.environ.get("SHIGA_LOAN_DOC_TITLE_CONTAINS", "").strip()
        or "ご融資資金返済予定明細表"
    )
    pdf_download_selector = os.environ.get("SHIGA_LOAN_PDF_DOWNLOAD_SELECTOR", "").strip()
    pdf_download_text = os.environ.get(
        "SHIGA_LOAN_PDF_DOWNLOAD_TEXT",
        "ご融資資金返済予定明細表",
    ).strip()
    amount_label = os.environ.get("SHIGA_LOAN_AMOUNT_LABEL", "借入残高").strip()
    output_dir = _resolve_output_dir(os.environ.get("SHIGA_LOAN_PDF_DIR", ""), env_file)
    fallback_pdf_path = _build_pdf_path(output_dir)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        context = browser.new_context(locale="ja-JP", accept_downloads=True)
        page = context.new_page()
        page.set_default_timeout(timeout_ms)
        page.goto(login_url, wait_until="domcontentloaded")
        _wait_page_ready(page, timeout_ms)
        try:
            page.wait_for_selector(username_selector, timeout=min(20000, timeout_ms))
        except Exception:
            pass

        def _login_in_root(root) -> bool:
            try:
                if username_selector and username and root.locator(username_selector).count() > 0:
                    root.locator(username_selector).fill(username)
                if password_selector and password and root.locator(password_selector).count() > 0:
                    root.locator(password_selector).fill(password)
                if submit_selector and (username_selector or password_selector):
                    if root.locator(submit_selector).count() > 0:
                        root.locator(submit_selector).click()
                        return True
            except Exception:
                return False
            return False

        if not _login_in_root(page):
            for fr in _frames_ordered(page):
                if fr is page.main_frame:
                    continue
                if _login_in_root(fr):
                    break
            else:
                try:
                    page.get_by_role("button", name="ログイン").click(timeout=timeout_ms)
                except Exception:
                    pass
        _wait_page_ready(page, timeout_ms)
        try:
            page.wait_for_load_state("networkidle", timeout=15000)
        except Exception:
            pass
        try:
            page.wait_for_timeout(2500)
        except Exception:
            pass
        for hint in ("お取引書類", "マイページ", "ご融資", "ローン"):
            try:
                page.get_by_text(hint, exact=False).first.wait_for(state="visible", timeout=5000)
                break
            except Exception:
                continue

        otp_root = page
        if otp_selector and page.locator(otp_selector).count() == 0:
            for fr in _frames_ordered(page):
                if fr.locator(otp_selector).count() > 0:
                    otp_root = fr
                    break

        if otp_selector and otp_root.locator(otp_selector).count() > 0:
            otp_code = _resolve_otp_code(otp_code_env, otp_code_override)
            if not otp_code:
                raise RuntimeError(
                    "ワンタイムパスワード入力ページです。対話実行で入力するか、"
                    "SHIGA_LOAN_OTP_CODE もしくは --otp-code を指定してください。"
                )
            otp_root.locator(otp_selector).fill(otp_code)
            if otp_submit_selector:
                sub = otp_root.locator(otp_submit_selector)
                if sub.count() == 0:
                    page.locator(otp_submit_selector).first.click()
                else:
                    sub.first.click()
            _wait_page_ready(page, timeout_ms)

        detail_dest = (target_url or "").strip() or _meisai_url_from_login(login_url)
        page.goto(detail_dest, wait_until="domcontentloaded")
        _wait_page_ready(page, timeout_ms)
        try:
            page.wait_for_load_state("networkidle", timeout=15000)
        except Exception:
            pass
        if to_detail_selector:
            try:
                loc = page.locator(to_detail_selector).first
                if loc.count() > 0:
                    loc.click(timeout=min(8000, timeout_ms))
                    _wait_page_ready(page, timeout_ms)
            except Exception:
                pass

        source_url = page.url

        try:
            page.wait_for_timeout(1500)
        except Exception:
            pass

        pdf_texts = _pdf_download_text_candidates(pdf_download_text)
        saved_paths: list[Path] = _download_schedule_pdfs_from_meisai_table(
            page,
            output_dir,
            doc_title_contains=doc_title_contains,
            timeout_ms=timeout_ms,
        )
        # 期待のPDFが1件しか取れない場合、一覧のPDFリンクを広めに落として内訳を拾う（セゾン/オリコ両方対策）
        if len(saved_paths) < 2:
            try:
                extra = _download_all_pdfs_from_meisai_table(page, output_dir, timeout_ms=timeout_ms)
                for pth in extra:
                    if pth not in saved_paths:
                        saved_paths.append(pth)
            except Exception:
                pass
        if not saved_paths:
            dl = _download_schedule_pdf_from_meisai_table(
                page,
                doc_title_contains=doc_title_contains,
                timeout_ms=timeout_ms,
            )
            if dl:
                try:
                    dl.save_as(str(fallback_pdf_path))
                    if fallback_pdf_path.exists():
                        saved_paths = [fallback_pdf_path]
                except Exception:
                    pass
        if not saved_paths:
            dl = _download_pdf_any_frame(
                page,
                selector=pdf_download_selector,
                text_candidates=pdf_texts,
                timeout_ms=timeout_ms,
            )
            if dl:
                try:
                    dl.save_as(str(fallback_pdf_path))
                    if fallback_pdf_path.exists():
                        saved_paths = [fallback_pdf_path]
                except Exception:
                    pass
        if not saved_paths:
            fallback_bytes = _download_by_link_fallback_any_frame(page, timeout_ms=timeout_ms)
            if fallback_bytes:
                fallback_pdf_path.write_bytes(fallback_bytes)
                if fallback_pdf_path.exists():
                    saved_paths = [fallback_pdf_path]

        if save_debug:
            DEFAULT_DEBUG_DIR.mkdir(parents=True, exist_ok=True)
            html_path = DEFAULT_DEBUG_DIR / "shiga_loan_last_page.html"
            png_path = DEFAULT_DEBUG_DIR / "shiga_loan_last_page.png"
            html_path.write_text(page.content(), encoding="utf-8")
            page.screenshot(path=str(png_path), full_page=True)

        browser.close()

    if not saved_paths:
        raise RuntimeError(
            "明細PDFの保存に失敗しました。「明細の確認」一覧の取得、"
            "SHIGA_LOAN_DOC_TITLE_CONTAINS、または SHIGA_LOAN_PDF_DOWNLOAD_SELECTOR / "
            "SHIGA_LOAN_PDF_DOWNLOAD_TEXT を見直してください。"
        )

    products: list[ShigaLoanProduct] = []
    for pth in saved_paths:
        products.extend(_products_from_pdf(pth, amount_label))
    # セゾン/オリコが取れている場合はその2つに絞る（他PDFが混ざる保険）
    by_kind: dict[str, ShigaLoanProduct] = {}
    for p in products:
        if p.kind in ("セゾンファイナンス", "オリコ") and int(p.amount_jpy) >= 1000:
            cur = by_kind.get(p.kind)
            if cur is None or int(p.amount_jpy) > int(cur.amount_jpy):
                by_kind[p.kind] = p
    if by_kind:
        products = list(by_kind.values())
    products = _sort_shiga_products(products)
    total_jpy = sum(int(p.amount_jpy) for p in products)
    amount_text = _format_shiga_amount_text(products, total_jpy)
    kinds = "+".join(p.kind for p in products)
    parser_mode = f"pdf:products:{kinds}"
    pdf_path_str = "; ".join(str(p) for p in saved_paths)
    return ShigaLoanResult(
        amount_jpy=total_jpy,
        amount_text=amount_text,
        source_url=source_url,
        parser_mode=parser_mode,
        pdf_path=pdf_path_str,
        products=products,
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="滋賀銀行ローン残高を取得")
    parser.add_argument("--headless", action="store_true", help="ヘッドレスで実行する")
    parser.add_argument("--timeout-ms", type=int, default=60000, help="Playwright タイムアウト（ms）")
    parser.add_argument("--save-debug", action="store_true", help="最終ページのHTML/PNGを保存")
    parser.add_argument(
        "--env-file",
        default=str(DEFAULT_ENV_PATH),
        help="環境変数ファイル（既定: finance/.env.lifeplan）",
    )
    parser.add_argument(
        "--otp-code",
        default="",
        help="ワンタイムパスワード。未指定で対話実行時は入力を促す",
    )
    parser.add_argument("--json", action="store_true", help="JSONで結果を出力する")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    try:
        result = fetch_shiga_loan_balance(
            headless=args.headless,
            timeout_ms=args.timeout_ms,
            save_debug=args.save_debug,
            env_file=Path(args.env_file).expanduser(),
            otp_code_override=(args.otp_code or "").strip() or None,
        )
    except PlaywrightTimeoutError as exc:
        print(f"タイムアウト: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"取得失敗: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(
            json.dumps(
                {
                    "amount_jpy": result.amount_jpy,
                    "amount_text": result.amount_text,
                    "source_url": result.source_url,
                    "parser_mode": result.parser_mode,
                    "pdf_path": result.pdf_path,
                    "products": [asdict(p) for p in result.products],
                },
                ensure_ascii=False,
            )
        )
    else:
        print(f"滋賀銀行ローン残高（合計）: {result.amount_jpy:,}円")
        for p in result.products:
            print(f"  - {p.kind}: {p.amount_jpy:,}円  ({p.amount_detail})")
        print(result.amount_text)
        print(f"保存PDF: {result.pdf_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
