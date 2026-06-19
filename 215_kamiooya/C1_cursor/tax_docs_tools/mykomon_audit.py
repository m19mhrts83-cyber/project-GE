#!/usr/bin/env python3
"""
MyKomon（税理士共有フォルダ）の提出ファイルを期間横断で走査し、
毎月必須の種目（PayPay / ミニテック / オリックス / クレカ）について
月次カバレッジを検証して抜け漏れを報告する（読み取り専用）。

使い方:
  python mykomon_audit.py \
      --start-month 2025-06 --end-month 2026-05 \
      --headless

決算期について:
  当法人は5月決算のため、確認サイクルは「6月〜翌5月」。
  --start-month / --end-month に期間を渡すことで毎年使い回せる。
  年度フォルダ（例: 2025年（令和7年））は暦年単位のため、
  6月〜翌5月の期間は2つの年度フォルダにまたがる。

認証情報: .env.tax_docs（同ディレクトリ）に
  MYKOMON_USER_ID / MYKOMON_PASSWORD を設定する。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import date
from pathlib import Path

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

# 既存のMyKomonナビゲーション関数を再利用
import mykomon_upload as mk

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_ENV_PATH = SCRIPT_DIR / ".env.tax_docs"

# OneDrive 側のレポート保存先（容量方針: git-repos には残さない）
DEFAULT_MATERIALS_ROOT = (
    Path.home()
    / "Library/CloudStorage/OneDrive-個人用/215_神・大家さん倶楽部"
    / "50_税金,確定申告/knees bee 税理士法人/2.経費,売上資料"
)

# 四半期フォルダ名（暦年内の月→四半期）
_QUARTER_LABELS = ["①1-3月", "②4-6月", "③7-9月", "④10-12月"]


# ---------------------------------------------------------------------------
# 種目・系列の設定
#   各カテゴリ: subfolder（任意）, series=系列リスト
#   各系列: name, match=マッチ語（いずれか含む）, cadence=monthly|asneeded
# ---------------------------------------------------------------------------
DEFAULT_CONFIG: dict = {
    "categories": [
        {
            "category": "01_預金通帳のコピー",
            "series": [
                {"name": "PayPay銀行明細", "match": ["PayPay", "ペイペイ"], "cadence": "monthly"},
            ],
        },
        {
            "category": "02_賃貸収入",
            "series": [
                {"name": "ミニテック送金のご案内", "match": ["ミニテック", "送金", "集金"], "cadence": "monthly"},
            ],
        },
        {
            "category": "05_借入金・保険・固定資産税",
            "series": [
                {"name": "オリックス返済実績表", "match": ["返済実績表", "オリックス"], "cadence": "monthly"},
                {"name": "保険・固定資産税ほか", "match": [], "cadence": "asneeded"},
            ],
        },
        {
            "category": "07_クレジットカード明細",
            "recurse_subfolders": True,
            "series": [
                {"name": "AMEX", "match": ["AMEX", "amex", "アメックス"], "cadence": "monthly"},
                {"name": "Vpass", "match": ["vpass", "Vpass", "VPASS"], "cadence": "monthly"},
            ],
        },
        # 発生時のみ（参考表示）
        {"category": "03_その他の収入", "series": [{"name": "その他収入", "match": [], "cadence": "asneeded"}]},
        {"category": "04_特殊なもの", "series": [{"name": "Finto広告費ほか", "match": [], "cadence": "asneeded"}]},
        {"category": "06_修繕費", "series": [{"name": "修繕費・工事完了報告書", "match": [], "cadence": "asneeded"}]},
        {"category": "08_現金で支払った領収書", "series": [{"name": "現金領収書", "match": [], "cadence": "asneeded"}]},
        {"category": "09_通帳口座から支払った領収書", "series": [{"name": "口座支払領収書", "match": [], "cadence": "asneeded"}]},
    ],
    # 欠落時の再抽出コマンドの雛形（系列名 → コマンド）
    "refill_hints": {
        "PayPay銀行明細": "tax_submit_paypay.py --months {months} --materials-root \"$MATERIALS\"",
        "ミニテック送金のご案内": "tax_submit_minitech.py --months {months} --materials-root \"$MATERIALS\"",
        "オリックス返済実績表": "tax_submit_orix.py --start-month {m} --end-month {m} --group G1 --materials-root \"$MATERIALS\"",
        "AMEX": "tax_submit_amex.py --periods missing-2025-06-2026-05 --materials-root \"$MATERIALS\"",
        "Vpass": "（Vpass明細を取得し 07_クレジットカード明細/取引が全て経費のもの へアップロード）",
    },
}


# ---------------------------------------------------------------------------
# 月レンジ・パーサ
# ---------------------------------------------------------------------------
def _ym_key(year: int, month: int) -> str:
    return f"{year}-{month:02d}"


def _month_range_set(
    start: tuple[int, int], end: tuple[int, int]
) -> set[tuple[int, int]]:
    """(年,月) start〜end（両端含む）の集合を返す。"""
    sy, sm = start
    ey, em = end
    result: set[tuple[int, int]] = set()
    y, m = sy, sm
    # 異常な範囲は空で返す
    if (ey, em) < (sy, sm):
        return result
    while (y, m) <= (ey, em):
        result.add((y, m))
        m += 1
        if m > 12:
            m = 1
            y += 1
    return result


def parse_months_from_name(
    name: str,
    default_year: int | None = None,
    window: set[tuple[int, int]] | None = None,
) -> set[tuple[int, int]]:
    """ファイル名から被覆する (年, 月) の集合を返す。

    年がファイル名に無い場合は default_year（そのファイルが置かれた
    フォルダの暦年）を補う。年なしの範囲がフォルダ年だと対象期間外に
    なる場合は、window（対象期間の月集合）に最も重なる年を選ぶ。

    対応する表記:
      - 単月: 6月 / 2025年6月 / 2025.6月 / 2025年 6月
      - 同年レンジ: 7月〜9月 / 4月-6月
      - 年跨ぎレンジ: 10月〜2026.3月 / 2025.10月〜2026.3月 / 10月〜4月
      - Vpass形式: 202510-202604（YYYYMMレンジ）/ 202506（単月）
    """
    covered: set[tuple[int, int]] = set()
    ctx_year = _first_year_in_name(name) or default_year

    # --- Vpass / YYYYMM レンジ: 202510-202604 ---
    for m in re.finditer(r"(20\d{2})(0[1-9]|1[0-2])\s*[-~〜]\s*(20\d{2})(0[1-9]|1[0-2])", name):
        sy, sm, ey, em = int(m.group(1)), int(m.group(2)), int(m.group(3)), int(m.group(4))
        covered |= _month_range_set((sy, sm), (ey, em))

    # --- 和文レンジ: <開始>月〜<終了>月（年跨ぎ・同年の両対応） ---
    # 例: 2025.10月〜2026.3月 / 10月〜2026.3月 / 7月〜9月 / 4月-6月 / 10月〜4月
    range_pat = re.compile(
        r"(?:(20\d{2})[年.\s]*)?(\d{1,2})月\s*[〜~\-－]\s*(?:(20\d{2})[年.\s]*)?(\d{1,2})月"
    )
    for m in range_pat.finditer(name):
        sy_raw, sm, ey_raw, em = m.group(1), int(m.group(2)), m.group(3), int(m.group(4))

        def _range_for(start_year: int) -> set[tuple[int, int]]:
            sy = start_year
            ey = int(ey_raw) if ey_raw else sy
            # 開始 > 終了（月が逆転）→ 終了年を翌年とみなす（年跨ぎ表記漏れ対策）
            if (ey, em) < (sy, sm):
                ey = sy + 1
            return _month_range_set((sy, sm), (ey, em))

        if sy_raw:
            covered |= _range_for(int(sy_raw))
        else:
            base = default_year or ctx_year
            if not base:
                continue
            # 年が無い範囲は、フォルダ年を基準にしつつ、対象期間に
            # 最も重なる開始年（前後1年）を採用する（誤フォルダ配置対策）
            if window:
                best, best_overlap = None, -1
                for cand in (base - 1, base, base + 1):
                    rng = _range_for(cand)
                    overlap = len(rng & window)
                    # 同点はフォルダ年(base)を優先
                    if overlap > best_overlap or (overlap == best_overlap and cand == base):
                        best, best_overlap = rng, overlap
                covered |= best if best is not None else _range_for(base)
            else:
                covered |= _range_for(base)

    if covered:
        return covered

    # --- 単月: 2025年6月 / 2025.6月 / 2025年 6月 ---
    for m in re.finditer(r"(20\d{2})[年.\s]*(\d{1,2})月", name):
        y, mo = int(m.group(1)), int(m.group(2))
        if 1 <= mo <= 12:
            covered.add((y, mo))
    if covered:
        return covered

    # --- 単月: YYYYMM 単体（202506） ---
    for m in re.finditer(r"(?<!\d)(20\d{2})(0[1-9]|1[0-2])(?!\d)", name):
        covered.add((int(m.group(1)), int(m.group(2))))
    if covered:
        return covered

    # --- 年省略の単月（6月 のみ）: 近傍年（無ければフォルダ年）を付与 ---
    if ctx_year:
        for m in re.finditer(r"(?<![0-9.])(\d{1,2})月", name):
            mo = int(m.group(1))
            if 1 <= mo <= 12:
                covered.add((ctx_year, mo))

    return covered


def _first_year_in_name(name: str) -> int | None:
    m = re.search(r"(20\d{2})", name)
    return int(m.group(1)) if m else None


# ---------------------------------------------------------------------------
# 期間 → 訪問フォルダの計画
# ---------------------------------------------------------------------------
def _year_label(calendar_year: int) -> str:
    reiwa = calendar_year - 2018
    return f"{calendar_year}年（令和{reiwa}年）"


def _quarter_for_month(month: int) -> str:
    return _QUARTER_LABELS[(month - 1) // 3]


def required_months(start: tuple[int, int], end: tuple[int, int]) -> list[tuple[int, int]]:
    return sorted(_month_range_set(start, end))


def visit_plan(months: list[tuple[int, int]]) -> list[tuple[str, str]]:
    """対象月から訪問すべき (年度ラベル, 四半期ラベル) の重複なしリストを作る。"""
    seen: list[tuple[str, str]] = []
    for (y, m) in months:
        key = (_year_label(y), _quarter_for_month(m))
        if key not in seen:
            seen.append(key)
    return seen


# ---------------------------------------------------------------------------
# MyKomon 走査
# ---------------------------------------------------------------------------
def _list_files_in_current_folder(page) -> list[str]:
    """現在の #inner_right に表示されているファイル名一覧を返す。

    MyKomon のDOM変更に強いよう、複数のセレクタを試し、
    最後に innerText から拡張子付きの行を拾うフォールバックを行う。
    """
    return page.evaluate(
        """() => {
            const inner = document.querySelector('#inner_right');
            if (!inner) return [];
            const out = new Set();

            // 1) ファイルダウンロードリンク系の代表的なセレクタ
            const selectors = [
                'a.download_file',
                'a.view_file',
                'a[onclick*="download"]',
                'a[href*="download"]',
            ];
            for (const sel of selectors) {
                for (const a of inner.querySelectorAll(sel)) {
                    const t = (a.innerText || '').trim();
                    if (t) out.add(t);
                }
            }
            if (out.size > 0) return [...out];

            // 2) フォールバック: innerText から拡張子付きトークンを拾う
            const text = inner.innerText || '';
            const re = /([^\\n\\t]+?\\.(?:pdf|PDF|xlsx|xls|csv|png|jpg|jpeg|zip|docx))/g;
            let m;
            while ((m = re.exec(text)) !== null) {
                out.add(m[1].trim());
            }
            return [...out];
        }"""
    )


def _position_name(page) -> str:
    """現在の #inner_right パンくず末尾（=現在地フォルダ名）を返す。"""
    return page.evaluate(
        """() => {
            const inner = document.querySelector('#inner_right');
            if (!inner) return '';
            const span = inner.querySelector('.title_area .position_name');
            return span ? span.innerText.trim() : '';
        }"""
    )


def _wait_position(page, expected: str, *, timeout_ms: int = 12000) -> bool:
    """パンくず末尾が expected になるまで待つ。"""
    import time
    deadline = time.time() + timeout_ms / 1000
    while time.time() < deadline:
        if _position_name(page) == expected:
            return True
        page.wait_for_timeout(400)
    return _position_name(page) == expected


def _click_listing_folder(page, name: str) -> bool:
    """一覧（パンくず以外）のフォルダリンクをクリック。"""
    return page.evaluate(
        """(name) => {
            const inner = document.querySelector('#inner_right');
            if (!inner) return false;
            const link = [...inner.querySelectorAll('a.view_folder')]
                .filter(a => !a.closest('.title_area'))
                .find(a => a.innerText.trim() === name);
            if (!link) return false;
            link.click();
            return true;
        }""",
        name,
    )


def _click_breadcrumb(page, name: str) -> bool:
    """パンくず内のフォルダリンクをクリック。"""
    return page.evaluate(
        """(name) => {
            const inner = document.querySelector('#inner_right');
            if (!inner) return false;
            const link = [...inner.querySelectorAll('.title_area a.view_folder')]
                .find(a => a.innerText.trim() === name);
            if (!link) return false;
            link.click();
            return true;
        }""",
        name,
    )


def _list_listing_subfolders(page) -> list[str]:
    """一覧の view_folder リンク名一覧（パンくず・ナビ系の重複あり）。"""
    return page.evaluate(
        """() => {
            const inner = document.querySelector('#inner_right');
            if (!inner) return [];
            const seen = new Set();
            const out = [];
            for (const a of inner.querySelectorAll('a.view_folder')) {
                if (a.closest('.title_area')) continue;
                const t = a.innerText.trim();
                if (!t || seen.has(t)) continue;
                seen.add(t);
                out.push(t);
            }
            return out;
        }"""
    )


# パンくず／ナビとして紛れ込む項目を除外するパターン
_NAV_NOISE_RE = re.compile(r"^(?:TOP|20\d{2}年|[\u2460-\u2473])")


def _real_subfolders(subs: list[str], *, exclude: set[str]) -> list[str]:
    """一覧リンクから、実体サブフォルダだけを抽出する。

    TOP / カラフルファイル… / 年度 / 四半期(①〜) / 自カテゴリ などの
    パンくず・ナビ由来のリンクを除外する。
    """
    out: list[str] = []
    for s in subs:
        if s in exclude:
            continue
        if "カラフルファイル" in s:
            continue
        if _NAV_NOISE_RE.match(s):
            continue
        out.append(s)
    return out


def _open_listing_folder(page, name: str, *, retries: int = 4) -> bool:
    """一覧のフォルダを開き、パンくずが name になるまで確認（リトライ付き）。"""
    for _ in range(retries):
        if _click_listing_folder(page, name):
            if _wait_position(page, name, timeout_ms=8000):
                return True
        page.wait_for_timeout(800)
    return False


def _goto_year(page, year: str, *, retries: int = 3) -> bool:
    """左ツリーで年度フォルダ（1階層）まで開く。深掘りはしない（遅延読込回避）。"""
    for _ in range(retries):
        try:
            mk._open_shared_folder_tab(page)
            mk._click_tree_path(page, "カラフルファイル（法人）", year)
        except Exception:
            pass
        if _wait_position(page, year, timeout_ms=8000):
            return True
        page.wait_for_timeout(600)
    return _position_name(page) == year


def _goto_quarter_listing(page, year: str, quarter: str) -> bool:
    """四半期一覧（カテゴリが並ぶ階層）に立つ。

    既に同四半期配下にいればパンくずで戻る（速い）。
    それ以外は 年度ツリー → 一覧で四半期を開く（深掘りツリーを避ける）。
    """
    if _click_breadcrumb(page, quarter) and _wait_position(page, quarter, timeout_ms=5000):
        return True
    if not _goto_year(page, year):
        return False
    return _open_listing_folder(page, quarter)


def _scan_quarter(
    page, *, year: str, quarter: str, categories: list[str]
) -> dict[str, list[str] | None]:
    """四半期配下の各カテゴリのファイル名を集約して返す。

    値が None のカテゴリは未作成（一覧に存在しない）。
    四半期一覧→一覧クリック→パンくず戻り、で高速・確実に巡回する。
    """
    result: dict[str, list[str] | None] = {}
    if not _goto_quarter_listing(page, year, quarter):
        raise RuntimeError(f"四半期に到達できません: {year}/{quarter}")

    present = set(_list_listing_subfolders(page))

    for cat in categories:
        if cat not in present:
            result[cat] = None
            continue

        # カテゴリを開く（失敗時は四半期から開き直す）
        if not _open_listing_folder(page, cat):
            if not (_goto_quarter_listing(page, year, quarter) and _open_listing_folder(page, cat)):
                raise RuntimeError(f"カテゴリを開けません: {cat}")

        files: list[str] = list(_list_files_in_current_folder(page))

        # サブフォルダ（クレカの「取引が全て経費のもの」等）を一段降りて集約
        nav_exclude = {quarter, year, cat} | set(categories)
        subfolders = _real_subfolders(
            _list_listing_subfolders(page), exclude=nav_exclude
        )
        for sub in subfolders:
            if not _open_listing_folder(page, sub):
                print(f"    ⚠ サブフォルダを開けません: {sub}")
                continue
            files.extend(_list_files_in_current_folder(page))
            # パンくずで category へ戻る（カテゴリ階層からは確実・高速）
            if not (_click_breadcrumb(page, cat) and _wait_position(page, cat, timeout_ms=5000)):
                if not (_goto_quarter_listing(page, year, quarter) and _open_listing_folder(page, cat)):
                    print(f"    ⚠ サブフォルダ後にカテゴリへ戻れません: {cat}")
                    break

        result[cat] = files

        # 次カテゴリのため四半期一覧へ戻る
        if not (_click_breadcrumb(page, quarter) and _wait_position(page, quarter, timeout_ms=5000)):
            _goto_quarter_listing(page, year, quarter)

    return result


# ---------------------------------------------------------------------------
# 監査本体
# ---------------------------------------------------------------------------
def run_audit(
    *,
    start: tuple[int, int],
    end: tuple[int, int],
    config: dict,
    headed: bool,
) -> dict:
    user_id = os.environ.get("MYKOMON_USER_ID", "")
    password = os.environ.get("MYKOMON_PASSWORD", "")
    if not all([user_id, password]):
        print(
            "エラー: MYKOMON_USER_ID / MYKOMON_PASSWORD が未設定です。\n"
            f"  → {DEFAULT_ENV_PATH} を確認してください",
            file=sys.stderr,
        )
        sys.exit(1)

    months = required_months(start, end)
    month_set = set(months)
    plan = visit_plan(months)

    # category -> list[(filename, folder_calendar_year)]（全訪問先で集約）
    category_files: dict[str, list[tuple[str, int]]] = {}

    print(f"対象期間: {_ym_key(*start)} 〜 {_ym_key(*end)}（{len(months)}ヶ月）")
    print(f"訪問フォルダ: {len(plan)} 件")
    for yl, ql in plan:
        print(f"  - {yl} / {ql}")

    categories = [c["category"] for c in config["categories"]]

    # 年度ごとにグルーピング（年度のツリー展開は1回で済むようにする）
    by_year: dict[str, list[str]] = {}
    for yl, ql in plan:
        by_year.setdefault(yl, [])
        if ql not in by_year[yl]:
            by_year[yl].append(ql)

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=not headed)
        context = browser.new_context()
        page = context.new_page()
        try:
            print("\n[1/2] MyKomon ログイン中...")
            mk._login(page, user_id, password)
            active = mk._find_shared_folder_target(page)

            print("\n[2/2] フォルダ走査...")
            for yl, quarters in by_year.items():
                cy_m = re.match(r"(20\d{2})", yl)
                cal_year = int(cy_m.group(1)) if cy_m else 0
                for ql in quarters:
                    try:
                        scanned = _scan_quarter(
                            active, year=yl, quarter=ql, categories=categories
                        )
                    except Exception as e:
                        print(f"  ⚠ {yl}/{ql}: 走査失敗（{e}）")
                        continue
                    for cat in categories:
                        files = scanned.get(cat)
                        if files is None:
                            print(f"  {yl}/{ql}/{cat}: （未作成）")
                            continue
                        category_files.setdefault(cat, [])
                        category_files[cat].extend((f, cal_year) for f in files)
                        print(f"  {yl}/{ql}/{cat}: {len(files)} 件")
        finally:
            context.close()
            browser.close()

    # 重複除去（複数四半期で同じファイルが見えることはないが念のため）
    for k in category_files:
        category_files[k] = sorted(set(category_files[k]))

    # 系列ごとにカバレッジを計算
    results = _evaluate_coverage(category_files, config, month_set)

    return {
        "start": start,
        "end": end,
        "months": months,
        "plan": plan,
        "category_files": category_files,
        "results": results,
    }


def _evaluate_coverage(
    category_files: dict[str, list[tuple[str, int]]],
    config: dict,
    month_set: set[tuple[int, int]],
) -> list[dict]:
    """系列ごとに被覆月・欠落月・該当ファイルを算出。

    category_files の各要素は (ファイル名, フォルダ暦年)。年が
    ファイル名に無い場合はフォルダ暦年を文脈として月を解釈する。
    """
    out: list[dict] = []
    for cat_conf in config["categories"]:
        cat = cat_conf["category"]
        files = category_files.get(cat, [])
        for series in cat_conf["series"]:
            match_words = series.get("match", [])
            cadence = series.get("cadence", "asneeded")
            if not match_words:
                # マッチ語なし系列は下の「その他ファイル」で扱う
                continue
            matched_files: list[str] = []
            covered: set[tuple[int, int]] = set()
            for fname, fyear in files:
                if not any(w in fname for w in match_words):
                    continue
                matched_files.append(fname)
                covered |= parse_months_from_name(
                    fname, default_year=fyear, window=month_set
                )
            covered_in_window = covered & month_set
            missing = sorted(month_set - covered_in_window) if cadence == "monthly" else []
            out.append({
                "category": cat,
                "series": series["name"],
                "cadence": cadence,
                "matched_files": matched_files,
                "covered": sorted(covered_in_window),
                "missing": missing,
            })

        # 参考: そのカテゴリで、どの monthly 系列にもマッチしなかったファイル
        monthly_words = [
            w for s in cat_conf["series"] if s.get("cadence") == "monthly"
            for w in s.get("match", [])
        ]
        leftover = [
            fname for fname, _ in files
            if not (monthly_words and any(w in fname for w in monthly_words))
        ]
        if leftover:
            out.append({
                "category": cat,
                "series": "（その他ファイル）",
                "cadence": "asneeded",
                "matched_files": leftover,
                "covered": [],
                "missing": [],
            })
    return out


# ---------------------------------------------------------------------------
# レポート生成
# ---------------------------------------------------------------------------
def _format_months(months: list[tuple[int, int]]) -> str:
    return ", ".join(_ym_key(y, m) for y, m in months)


def build_report(audit: dict, config: dict) -> str:
    start, end = audit["start"], audit["end"]
    months = audit["months"]
    results = audit["results"]
    lines: list[str] = []

    lines.append(f"# MyKomon 抜け漏れチェック {_ym_key(*start)}〜{_ym_key(*end)}")
    lines.append("")
    lines.append(f"- 対象期間: {_ym_key(*start)} 〜 {_ym_key(*end)}（{len(months)}ヶ月・5月決算サイクル）")
    lines.append(f"- 生成日時: {date.today().isoformat()}")
    lines.append("")

    # --- 月次必須のカバレッジ表 ---
    lines.append("## 月次必須カバレッジ（○=あり / ✗=欠落）")
    lines.append("")
    header = "| 系列 | " + " | ".join(f"{m:02d}" if False else f"{y%100}/{m:02d}" for y, m in months) + " |"
    sep = "|---|" + "---|" * len(months)
    lines.append(header)
    lines.append(sep)

    monthly_results = [r for r in results if r["cadence"] == "monthly"]
    for r in monthly_results:
        covered = set(tuple(x) for x in r["covered"])
        cells = []
        for (y, m) in months:
            cells.append("○" if (y, m) in covered else "✗")
        lines.append(f"| {r['series']} | " + " | ".join(cells) + " |")
    lines.append("")

    # --- 欠落一覧 ---
    has_missing = any(r["missing"] for r in monthly_results)
    lines.append("## 欠落（要対応）")
    lines.append("")
    if not has_missing:
        lines.append("欠落はありません。月次必須の4系列すべてが期間内で揃っています。")
    else:
        refill = config.get("refill_hints", {})
        for r in monthly_results:
            if not r["missing"]:
                continue
            miss = r["missing"]
            lines.append(f"### {r['category']} / {r['series']}")
            lines.append(f"- 欠落月: {_format_months(miss)}")
            hint = refill.get(r["series"])
            if hint:
                months_arg = ",".join(_ym_key(y, m) for y, m in miss)
                # オリックスは単月指定型のため最初の月を例示
                first = _ym_key(*miss[0])
                cmd = hint.replace("{months}", months_arg).replace("{m}", first)
                lines.append(f"- 再抽出の例: `{cmd}`")
            lines.append("")
    lines.append("")

    # --- 検出ファイル（系列別）: ✗判定の検証用 ---
    lines.append("## 検出ファイル（系列別）")
    lines.append("")
    for r in monthly_results:
        lines.append(f"- {r['category']} / {r['series']}（{len(r['matched_files'])} 件）")
        if not r["matched_files"]:
            lines.append("    - （該当ファイルなし）")
        for f in r["matched_files"]:
            lines.append(f"    - {f}")
    lines.append("")

    # --- 参考: 発生時のみ種目／その他ファイル ---
    lines.append("## 参考（発生時のみ・その他ファイル）")
    lines.append("")
    asneeded = [r for r in results if r["cadence"] == "asneeded"]
    if not asneeded:
        lines.append("（なし）")
    else:
        for r in asneeded:
            if not r["matched_files"]:
                continue
            lines.append(f"- {r['category']} / {r['series']}: {len(r['matched_files'])} 件")
            for f in r["matched_files"]:
                lines.append(f"    - {f}")
    lines.append("")

    return "\n".join(lines)


def print_console_summary(audit: dict) -> None:
    months = audit["months"]
    results = audit["results"]
    monthly = [r for r in results if r["cadence"] == "monthly"]

    print("\n" + "=" * 70)
    print("  月次必須カバレッジ")
    print("=" * 70)
    head = "系列".ljust(22) + " " + " ".join(f"{y%100:02d}/{m:02d}" for y, m in months)
    print(head)
    for r in monthly:
        covered = set(tuple(x) for x in r["covered"])
        cells = []
        for (y, m) in months:
            cells.append("  ○ " if (y, m) in covered else "  ✗ ")
        print(r["series"].ljust(22) + " " + " ".join(c.strip().center(5) for c in cells))

    print("\n" + "=" * 70)
    print("  欠落（要対応）")
    print("=" * 70)
    any_missing = False
    for r in monthly:
        if r["missing"]:
            any_missing = True
            print(f"  {r['category']} / {r['series']}: {_format_months(r['missing'])}")
    if not any_missing:
        print("  欠落なし。4系列すべて期間内で揃っています。")


def save_report(report: str, materials_root: Path, start: tuple[int, int], end: tuple[int, int]) -> Path:
    out_dir = materials_root / "_チェック"
    out_dir.mkdir(parents=True, exist_ok=True)
    fname = f"MyKomon抜け漏れ_{start[0]}.{start[1]}-{end[0]}.{end[1]}.md"
    dest = out_dir / fname
    dest.write_text(report, encoding="utf-8")
    return dest


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def _parse_month(s: str) -> tuple[int, int]:
    parts = s.split("-")
    if len(parts) != 2:
        raise ValueError(f"月の形式が不正です: {s}（YYYY-MM）")
    return int(parts[0]), int(parts[1])


def main() -> None:
    parser = argparse.ArgumentParser(
        description="MyKomon 抜け漏れチェック（年次・最終チェック）",
    )
    parser.add_argument("--start-month", required=True, help="開始月（YYYY-MM。例: 2025-06）")
    parser.add_argument("--end-month", required=True, help="終了月（YYYY-MM。例: 2026-05）")
    parser.add_argument(
        "--materials-root", default=str(DEFAULT_MATERIALS_ROOT),
        help="2.経費,売上資料 フォルダのパス（レポート保存先）",
    )
    parser.add_argument(
        "--config", default="",
        help="種目・系列設定のJSONファイル（省略時は内蔵設定）",
    )
    parser.add_argument("--env-file", default=str(DEFAULT_ENV_PATH))
    parser.add_argument("--headless", action="store_true", help="ヘッドレスで実行")
    parser.add_argument("--no-save", action="store_true", help="レポートをファイル保存しない")
    args = parser.parse_args()

    mk._load_env_file(Path(args.env_file))

    start = _parse_month(args.start_month)
    end = _parse_month(args.end_month)

    config = DEFAULT_CONFIG
    if args.config:
        config = json.loads(Path(args.config).read_text(encoding="utf-8"))

    audit = run_audit(start=start, end=end, config=config, headed=not args.headless)

    print_console_summary(audit)

    report = build_report(audit, config)
    if not args.no_save:
        dest = save_report(report, Path(args.materials_root), start, end)
        print(f"\nレポートを保存しました: {dest}")


if __name__ == "__main__":
    main()
