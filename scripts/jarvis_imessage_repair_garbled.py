#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""iMessage の「化けブロック」を復元する（attributedBody の誤デコード対策）。

対象: 各パートナー `5.やり取り.md` のうち、本文が NSAttributedString のダンプ
      （`streamtyped NSAttributedString…` / `#$_NS.rangeval…`）や NUL 等の制御文字に
      なっているブロック。

方法: `chat.db` の (日時 JST, from_me) で該当メッセージを引き、
      `imessage_to_yoritoori.try_parse_attributed_body`（NSString→0x2b→可変長長）で
      復号した本文に置換する。ファイル全体の NUL/制御文字も除去する。

使い方:
  cd ~/git-repos && set -a && source .env.jarvis_private && set +a
  ~/selenium_env/venv/bin/python scripts/jarvis_imessage_repair_garbled.py           # dry-run
  ~/selenium_env/venv/bin/python scripts/jarvis_imessage_repair_garbled.py --apply
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
MANUAL = REPO / "215_kamiooya" / "C1_cursor" / "1b_Cursorマニュアル"
if str(MANUAL) not in sys.path:
    sys.path.insert(0, str(MANUAL))

from imessage_to_yoritoori import (  # noqa: E402
    BASE_DIR,
    YORITOORI_FILENAME,
    _load_phone_to_partner,
    _open_chat_db,
    format_date_from_apple_ns,
    try_parse_attributed_body,
)
from yoritoori_utils import make_summary  # noqa: E402

MARKERS = (
    "streamtyped",
    "NS.rangeval",
    "#$_NS",
    "NSMutableAttributedString",
    "NSAttributedString",
)
HEADING_RE = re.compile(r"^### (\d{4}/\d{2}/\d{2} \d{2}:\d{2})｜([^｜]+)｜([^｜]+)(?:｜(.*))?$")


def _has_control(s: str) -> bool:
    return any(ord(c) < 0x20 and c not in "\n\t" for c in s)


def looks_garbled(body: str) -> bool:
    return any(m in body for m in MARKERS) or _has_control(body)


def strip_controls(s: str) -> str:
    return "".join(c for c in s if c in "\n\t" or ord(c) >= 0x20)


def build_index() -> dict[tuple[str, int], list[str]]:
    conn = _open_chat_db()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT m.text, m.date, m.attributedBody, m.is_from_me
        FROM message m
        JOIN handle h ON m.handle_id = h.ROWID
        """
    )
    index: dict[tuple[str, int], list[str]] = {}
    for text, date_ns, ab, is_from_me in cur.fetchall():
        body = (text or "").strip()
        if not body:
            body = try_parse_attributed_body(ab) or ""
        if not body:
            continue
        key = (format_date_from_apple_ns(date_ns), int(is_from_me or 0))
        index.setdefault(key, []).append(body)
    conn.close()
    return index


def repair_file(path: Path, index: dict[tuple[str, int], list[str]], apply: bool) -> tuple[int, bool]:
    """戻り値: (置換したブロック数, ファイルを書き換えたか)"""
    raw = path.read_bytes()
    text = raw.decode("utf-8", errors="replace")
    lines = text.split("\n")
    used: set[tuple[str, int, int]] = set()
    changed = 0

    i = 0
    out: list[str] = []
    while i < len(lines):
        line = lines[i]
        m = HEADING_RE.match(line)
        if not m:
            out.append(line)
            i += 1
            continue
        out.append(line)
        ts, partner, direction, _summary = m.group(1), m.group(2), m.group(3), m.group(4)
        # 「自分から送信」→ 1 /「相手から返信」→ 0
        is_from_me = 1 if "自分" in direction else 0
        # 本文ブロックを収集（次の見出し or '---' まで）
        j = i + 1
        block: list[str] = []
        while j < len(lines) and not lines[j].startswith("### ") and lines[j].strip() != "---":
            block.append(lines[j])
            j += 1
        body = "\n".join(block).strip()
        if body and looks_garbled(body):
            cand = index.get((ts, is_from_me), [])
            pick = None
            for k, text_cand in enumerate(cand):
                if (ts, is_from_me, k) not in used:
                    pick = text_cand
                    used.add((ts, is_from_me, k))
                    break
            if pick:
                new_heading = (
                    f"### {ts}｜{partner}｜{direction}｜{make_summary(pick, max_len=40)}"
                )
                out[-1] = new_heading
                out.append("")
                out.append(strip_controls(pick).strip())
                out.append("")
                changed += 1
                print(f"    - {ts}｜{partner}｜{direction} → {pick[:40]}")
                i = j
                continue
        out.extend(block)
        i = j

    new_text = "\n".join(out)
    if _has_control(new_text):
        new_text = strip_controls(new_text)
    touched = new_text != text
    if touched and apply:
        path.write_text(new_text, encoding="utf-8")
    return changed, touched


def main() -> int:
    ap = argparse.ArgumentParser(description="iMessage 化けブロックの復元")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--partner", help="パートナー名で絞る")
    args = ap.parse_args()

    phone_to_partner = _load_phone_to_partner(args.partner)
    folders = {p["folder"]: p["name"] for p in phone_to_partner.values() if p.get("folder")}
    if not folders:
        print("対象パートナーがありません")
        return 0

    index = build_index()
    print(f"# chat.db 復号インデックス: {len(index)} 時刻キー")
    total = 0
    touched_files = 0
    for folder, name in folders.items():
        path = BASE_DIR / folder / YORITOORI_FILENAME
        if not path.is_file():
            continue
        changed, touched = repair_file(path, index, args.apply)
        if changed or touched:
            total += changed
            touched_files += 1
            print(
                f"{'[APPLY]' if args.apply else '[dry-run]'} {name} ({folder}): "
                f"置換 {changed} ブロック / 制御文字{'除去' if touched and not changed else '変更なし'}"
            )
    print(f"合計 {total} ブロック / {touched_files} ファイル" + ("" if args.apply else "（dry-run・--apply で書き込み）"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
