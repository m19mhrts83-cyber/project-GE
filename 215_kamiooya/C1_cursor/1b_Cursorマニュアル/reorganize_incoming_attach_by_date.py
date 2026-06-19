#!/usr/bin/env python3
"""1.受信添付(Stock) 内のファイルを受信日フォルダ YYYY-MM-DD へ整理する（一回限り／メンテ用）。"""

from __future__ import annotations

import argparse
import os
import re
import shutil
from datetime import datetime
from pathlib import Path

from yoritoori_utils import YORITOORI_FILENAME, default_yoritoori_base_dir, parse_received_date_folder

DATE_DIR_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
PREFIX_DATE_RE = re.compile(r"^(\d{4})(\d{2})(\d{2})_")
EMBED_DATE_RE = re.compile(r"(?<!\d)(\d{4})(\d{2})(\d{2})(?!\d)")
MAIL_DATE_RE = re.compile(r"メール日時:\s*(\d{4})[/-](\d{2})[/-](\d{2})")
ATTACH_LINE_RE = re.compile(r"\*\*添付ファイル\*\*:\s*(.+)")
BLOCK_HEADER_RE = re.compile(r"^### (\d{4}/\d{2}/\d{2})")


def _to_folder(y: str, m: str, d: str) -> str:
    return f"{y}-{m}-{d}"


def date_from_filename(name: str) -> str | None:
    m = PREFIX_DATE_RE.match(name)
    if m:
        return _to_folder(*m.groups())
    m = EMBED_DATE_RE.search(name)
    if m:
        y, mo, da = m.groups()
        if 2020 <= int(y) <= 2035 and 1 <= int(mo) <= 12 and 1 <= int(da) <= 31:
            return _to_folder(y, mo, da)
    return None


def build_yoritoori_index(md_path: Path) -> dict[str, str]:
    """ファイル名（basename）→ YYYY-MM-DD"""
    if not md_path.exists():
        return {}
    index: dict[str, str] = {}
    current_date: str | None = None
    for line in md_path.read_text(encoding="utf-8").splitlines():
        hm = BLOCK_HEADER_RE.match(line.strip())
        if hm:
            current_date = hm.group(1).replace("/", "-")
            continue
        am = ATTACH_LINE_RE.search(line)
        if not am or not current_date:
            continue
        raw = am.group(1).split("（")[0]
        for part in re.split(r",\s*", raw):
            part = part.strip()
            if not part or part == ".gitkeep":
                continue
            base = Path(part).name
            d = date_from_filename(base) or current_date
            index[base] = d
            index[part] = d
    return index


def resolve_date(path: Path, stock: Path, yoritoori_index: dict[str, str]) -> str:
    name = path.name
    d = date_from_filename(name)
    if d:
        return d
    if name in yoritoori_index:
        return yoritoori_index[name]
    rel = str(path.relative_to(stock))
    if rel in yoritoori_index:
        return yoritoori_index[rel]
    if name.endswith("_download_info.txt"):
        text = path.read_text(encoding="utf-8", errors="replace")
        m = MAIL_DATE_RE.search(text)
        if m:
            return _to_folder(*m.groups())
    ts = path.stat().st_mtime
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d")


def collect_stock_dirs(base: Path) -> list[Path]:
    dirs: list[Path] = []
    for root, subdirs, _files in os.walk(base):
        if Path(root).name in ("1.受信添付(Stock)", "添付"):
            # 815 オプチャ配下は対象外
            if "815_神大家オプチャ" in root.replace("\\", "/"):
                continue
            dirs.append(Path(root))
    return sorted(set(dirs))


def reorganize_stock(stock: Path, dry_run: bool) -> list[tuple[str, str, str]]:
    """returns list of (old_rel, new_rel, partner_hint)"""
    partner_dir = stock.parent
    md_path = partner_dir / YORITOORI_FILENAME
    yoritoori_index = build_yoritoori_index(md_path)
    moves: list[tuple[Path, Path]] = []

    for path in sorted(stock.rglob("*")):
        if not path.is_file() or path.name == ".gitkeep":
            continue
        rel_parts = path.relative_to(stock).parts
        if rel_parts and DATE_DIR_RE.match(rel_parts[0]):
            continue
        day = resolve_date(path, stock, yoritoori_index)
        dest_dir = stock / day
        dest = dest_dir / path.name
        if dest.resolve() == path.resolve():
            continue
        counter = 0
        while dest.exists() and dest.stat().st_size != path.stat().st_size:
            counter += 1
            dest = dest_dir / f"{path.stem}_{counter}{path.suffix}"
        moves.append((path, dest))

    report: list[tuple[str, str, str]] = []
    for src, dest in moves:
        rel_old = str(src.relative_to(stock))
        rel_new = str(dest.relative_to(stock))
        report.append((rel_old, rel_new, partner_dir.name))
        if not dry_run:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src), str(dest))

    if not dry_run:
        for d in sorted(stock.rglob("*"), reverse=True):
            if d.is_dir() and d != stock and not any(d.iterdir()):
                d.rmdir()
        update_yoritoori_paths(md_path, report)

    return report


def update_yoritoori_paths(md_path: Path, moves: list[tuple[str, str, str]]) -> None:
    if not md_path.exists() or not moves:
        return
    text = md_path.read_text(encoding="utf-8")
    orig = text
    # 長いパスから置換（部分一致を防ぐ）
    for old, new, _ in sorted(moves, key=lambda x: len(x[0]), reverse=True):
        if old in text:
            text = text.replace(old, new)
        old_base = Path(old).name
        if old_base != old and old_base in text:
            text = re.sub(
                rf"(?<![/\w]){re.escape(old_base)}(?![/\w])",
                new,
                text,
            )
    if text != orig:
        md_path.write_text(text, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="受信添付を YYYY-MM-DD フォルダへ整理")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--base", type=Path, default=None)
    args = parser.parse_args()
    base = args.base or default_yoritoori_base_dir()

    all_moves: list[tuple[str, str, str]] = []
    for stock in collect_stock_dirs(base):
        moves = reorganize_stock(stock, dry_run=args.dry_run)
        if moves:
            print(f"\n## {stock.parent.name}")
            for old, new, _ in moves:
                print(f"  {old} → {new}")
            all_moves.extend(moves)

    print(f"\n合計: {len(all_moves)} 件{' (dry-run)' if args.dry_run else ''}")


if __name__ == "__main__":
    main()
