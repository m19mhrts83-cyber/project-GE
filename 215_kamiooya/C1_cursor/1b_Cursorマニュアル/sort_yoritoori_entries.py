#!/usr/bin/env python3
"""
やり取り.md のエントリを時系列で新しい順に並び替える。
テンプレート（### 20XX/XX/XX）はそのまま、実エントリ（### 2026/02/11 等）のみソートする。

使い方: python sort_yoritoori_entries.py
"""

import re
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent / "C2_ルーティン作業" / "26_パートナー社への相談"
YORITOORI_FILENAME = "5.やり取り.md"


def parse_sort_key(first_line):
    """
    ### 2026/02/11｜ or ### 2026/02/13 22:00｜ からソート用のタプルを返す。
    パースできない（20XX等）は None を返し、テンプレートとして扱う。
    """
    m = re.match(r"^### (\d{4})/(\d{2})/(\d{2})(?:\s+(\d{1,2}):(\d{2}))?｜", first_line)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        h = int(m.group(4) or 0)
        mi = int(m.group(5) or 0)
        return (y, mo, d, h, mi)
    return None


def split_into_blocks(body):
    """本文をブロック（### で始まる単位）に分割。"""
    blocks = []
    current = []
    for line in body.split("\n"):
        if re.match(r"^### ", line):
            if current:
                blocks.append("\n".join(current))
            current = [line]
        else:
            current.append(line)
    if current:
        blocks.append("\n".join(current))
    return blocks


def sort_yoritoori_file(md_path):
    """やり取り.md を新しい順に並び替え。"""
    content = md_path.read_text(encoding="utf-8")
    if "## やり取り（時系列）" not in content:
        return False, "セクション見つからず"

    parts = content.split("## やり取り（時系列）", 1)
    header = parts[0] + "## やり取り（時系列）\n\n"
    body = parts[1]

    blocks = split_into_blocks(body)
    template_blocks = []
    real_blocks = []

    for b in blocks:
        first_line = b.split("\n")[0]
        key = parse_sort_key(first_line)
        if key is not None:
            real_blocks.append((key, b))
        else:
            template_blocks.append(b)

    real_blocks.sort(key=lambda x: x[0], reverse=True)

    result = header
    for t in template_blocks:
        result += t.rstrip() + "\n\n"
    for _, b in real_blocks:
        result += b.rstrip() + "\n\n"
    result = result.rstrip() + "\n"

    md_path.write_text(result, encoding="utf-8")
    return True, f"実エントリ {len(real_blocks)} 件を新しい順に並び替え"


def main():
    for folder in sorted(BASE_DIR.iterdir()):
        if not folder.is_dir() or folder.name.startswith("000"):
            continue
        md_path = folder / YORITOORI_FILENAME
        if not md_path.exists():
            continue
        ok, msg = sort_yoritoori_file(md_path)
        if ok:
            print(f"{folder.name}: {msg}")
        else:
            print(f"{folder.name}: {msg}")


if __name__ == "__main__":
    main()
