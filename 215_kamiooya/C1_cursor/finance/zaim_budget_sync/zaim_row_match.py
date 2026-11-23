#!/usr/bin/env python3
"""
Zaim 日別一覧の行を「ちょうど1件」に絞るための純粋ロジック（Playwright 非依存・CI でテスト可）。

画面側（zaim_money_edit.py）は DOM から行を dict に抜き出し、ここで絞り込む。
2026-11-24 の画面診断（DOM）に基づく:
  - 行: div.SearchResult-module__body（class 末尾にハッシュ）
  - 編集アイコン: edit セルの i[data-url="/money/{ID}/edit"]（明細IDが出る）
  - 集計アイコン: calc セルの i。緑 add_circle_outline=常に含める(標準) / 灰 not_interested=常に含めない
  - 金額: price セルの「¥1,234」
  - 出金元: fromAccount セルの img alt
絞れない（0件・複数件）ときは None を返し、呼び出し側は何も変更せず止める。
"""
from __future__ import annotations

import re
import unicodedata
from typing import Any

CALC_INCLUDE = "add_circle_outline"  # 常に含める（標準）
CALC_EXCLUDE = "not_interested"  # 常に含めない

# 集計アイコンの title／モーダル select の value 対応
AGG_TITLE_TO_VALUE = {
    "常に含める（標準）": "10",
    "月ごと・年ごとのみ含める": "6",
    "年ごとのみ含める": "3",
    "常に含めない": "0",
}
AGG_VALUE_TO_CALC = {
    "10": CALC_INCLUDE,
    "0": CALC_EXCLUDE,
}

# 「ちょうど1件」にならなかった理由コード（人向けの短い日本語）
R_NO_PRICE = "金額が一致する行がない"
R_NO_ACCOUNT = "出金元が一致する行がない"
R_NO_SHOP = "お店が一致する行がない"
R_GROUP_SIZE = "同額の行数が想定と違う"
R_CALC = "集計の状態が想定と違う"
R_DESCRIBED = "品目・メモの有無で1件に絞れない"
R_MANY = "複数の行が残った"
R_NO_ROWS = "日別一覧に行が出ない"
R_ID_NOT_FOUND = "明細IDの行が見つからない"


def nf(s: str | None) -> str:
    s = unicodedata.normalize("NFKC", (s or "").strip())
    s = s.replace("…", "").replace("...", "")
    return re.sub(r"\s+", "", s).lower()


def parse_yen(text: str | None) -> int | None:
    """『¥1,234』→1234。数字が無ければ None。"""
    m = re.search(r"(\d[\d,]*)", unicodedata.normalize("NFKC", text or ""))
    if not m:
        return None
    try:
        return int(m.group(1).replace(",", ""))
    except ValueError:
        return None


def price_matches_exactly(price_text: str | None, amount: int) -> bool:
    """¥金額 の完全一致（部分一致で ¥11,000 を ¥1,000 と取り違えない）。"""
    raw = unicodedata.normalize("NFKC", (price_text or "")).strip()
    raw = re.sub(r"[¥￥\s]", "", raw)
    return raw == f"{amount:,}"


def edit_id_from_url(url: str | None) -> str | None:
    m = re.search(r"/money/(\d+)/edit", url or "")
    return m.group(1) if m else None


def account_matches(alt: str | None, pay: str | None) -> bool:
    """出金元 alt と CSV の支払元。pay は 40 文字で切れていることがあるため前方一致も許す。"""
    a, p = nf(alt), nf(pay)
    if not a or not p:
        return False
    return a == p or a.startswith(p) or p.startswith(a)


def shop_matches(place: str | None, shop: str | None) -> bool:
    p, s = nf(place), nf(shop)
    if not s:
        return True
    if not p:
        return False
    n = min(6, len(s), len(p))
    return p[:n] == s[:n] or s in p or p in s


def is_described(row: dict[str, Any]) -> bool:
    """品目またはメモが空でない（記述あり）。"""
    return bool(nf(row.get("name")) or nf(row.get("comment")))


def select_row(
    rows: list[dict[str, Any]],
    *,
    amount: int,
    pay: str = "",
    shop: str = "",
    expect_calc: str | None = None,
    described: bool | None = None,
    group_size: int | None = 1,
) -> tuple[dict[str, Any] | None, str]:
    """
    rows: {price, calc, acct, place, name, comment, edit_url, index} の一覧。
    戻り値: (選んだ行 or None, 理由)。ちょうど1件でなければ None。

    group_size: 金額＋出金元＋お店で絞った行数が何件のはずか（型A=1、型B=2、None=見ない）。
    expect_calc: 選ぶ行の calc（集計除外=緑 CALC_INCLUDE）。None なら見ない（費目変更など）。
    described: True=記述あり側 / False=記述なし側 / None=見ない。
    """
    cand = [r for r in rows if price_matches_exactly(r.get("price"), amount)]
    if not cand:
        return None, R_NO_PRICE
    if pay:
        cand = [r for r in cand if account_matches(r.get("acct"), pay)]
        if not cand:
            return None, R_NO_ACCOUNT
    if shop:
        cand = [r for r in cand if shop_matches(r.get("place"), shop)]
        if not cand:
            return None, R_NO_SHOP
    if group_size is not None and len(cand) != group_size:
        return None, f"{R_GROUP_SIZE}（{len(cand)}件）"
    if expect_calc is not None:
        cand = [r for r in cand if r.get("calc") == expect_calc]
        if not cand:
            return None, R_CALC
    if described is not None:
        cand = [r for r in cand if is_described(r) == described]
        if not cand:
            return None, R_DESCRIBED
    if len(cand) != 1:
        return None, f"{R_MANY}（{len(cand)}件）" if len(cand) > 1 else R_DESCRIBED
    if not edit_id_from_url(cand[0].get("edit_url")):
        return None, R_ID_NOT_FOUND
    return cand[0], "ok"


def find_by_id(rows: list[dict[str, Any]], zaim_id: str) -> dict[str, Any] | None:
    hit = [r for r in rows if edit_id_from_url(r.get("edit_url")) == str(zaim_id)]
    return hit[0] if len(hit) == 1 else None


def modal_ready(snap: dict[str, Any] | None, zaim_id: str) -> bool:
    """編集モーダルの中身が入り、その行（明細ID）のフォームである。"""
    if not snap or not snap.get("open"):
        return False
    if snap.get("spinner_visible"):
        return False
    if not snap.get("content_children"):
        return False
    return any(str(zaim_id) in str(a or "") for a in (snap.get("form_actions") or []))


def verify_calc(rows: list[dict[str, Any]], zaim_id: str, expected_calc: str) -> tuple[bool, str]:
    """保存後に日別を再読み込みして、同じ明細IDの行の calc が期待どおりか。"""
    row = find_by_id(rows, zaim_id)
    if row is None:
        return False, R_ID_NOT_FOUND
    if row.get("calc") == expected_calc:
        return True, "ok"
    return False, f"集計アイコンが想定と違う（{row.get('calc')}）"


def agg_value_from_title(title: str | None) -> str | None:
    return AGG_TITLE_TO_VALUE.get((title or "").strip())
