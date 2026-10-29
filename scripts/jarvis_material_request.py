#!/usr/bin/env python3
"""「資料を送ってください」系の依頼を検出し、依頼品目を抜き出す（LLM なし）。

TS 側 apps/jarvis-dashboard/lib/materialRequest.ts と同じ規則。
"""
from __future__ import annotations

import re

REQUEST_RE = re.compile(
    r"(ご提出|ご送付|お送り(いただ|くださ)|ご準備|ご用意|添付(して|の上)|送って(いただ|くださ)|ご提示)"
)
MATERIAL_RE = re.compile(r"(資料|書類|証明書|写し|コピー|通帳|申込書|申告書|明細|図面|謄本|見積)")
LEAD_RE = re.compile(r"(下記|以下|次の).{0,20}(資料|書類|ご提出|ご準備|ご用意|お願い)")
BULLET_RE = re.compile(r"^\s*(?:[・•\-*]|[0-9０-９]+[.．)）]|[①-⑳])\s*(.+)$")
QUOTE_RE = re.compile(r"^(>|-{3,}\s*Original|From:|差出人:|\d{4}年\d{1,2}月\d{1,2}日.*\d{1,2}:\d{2})")
CLOSE_RE = re.compile(r"(よろしくお願い|宜しくお願い|以上|ご確認のほど)")
MAX_ITEMS = 10


def _main_text(body: str) -> list[str]:
    out: list[str] = []
    for line in (body or "").splitlines():
        if QUOTE_RE.match(line.strip()):
            break
        out.append(line.rstrip())
    return out


def extract_material_requests(body: str) -> list[str]:
    """依頼された資料の品目。依頼でなければ空。"""
    lines = _main_text(body)
    text = "\n".join(lines)
    if not (REQUEST_RE.search(text) and MATERIAL_RE.search(text)):
        return []
    items: list[str] = []
    in_block = False
    block_n = 0
    for line in lines:
        s = line.strip().strip("　")
        if not s:
            # 一覧の後の空行で区切る（一覧の前の空行は許す）
            if in_block and block_n:
                in_block = False
            continue
        if s.startswith(("＊", "*", "■", "━", "＝", "=", "-----")):
            # 区切り線は一覧の終わり（一覧の前なら読み飛ばす）
            if in_block and block_n:
                in_block = False
            continue
        if s.startswith(("※", "（※", "(※")):
            continue
        m = BULLET_RE.match(s)
        if m and (in_block or MATERIAL_RE.search(s)):
            items.append(m.group(1).strip())
            block_n += 1
            continue
        if LEAD_RE.search(s):
            in_block, block_n = True, 0
            continue
        if in_block:
            if CLOSE_RE.search(s) or len(s) > 60:
                in_block = False
                continue
            items.append(s)
            block_n += 1
    seen: set[str] = set()
    uniq = []
    for it in items:
        it = it[:80]
        if it and it not in seen:
            seen.add(it)
            uniq.append(it)
    if not uniq:
        # 依頼文はあるが一覧が取れないときは、依頼のある1文を品目代わりに
        for s in (l.strip() for l in lines):
            if REQUEST_RE.search(s) and MATERIAL_RE.search(s):
                return [s[:80]]
    return uniq[:MAX_ITEMS]
