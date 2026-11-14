# -*- coding: utf-8 -*-
"""GitHub Pages に出すファイルを選ぶ（2026-11-14 314）。

これまでは docs/ を丸ごと公開していたので、取引先とのやり取りや社員の output（.md 等）まで
誰でも読めた。公開するのは docs/ 配下の HTML と、その HTML が相対パスで読み込むファイルだけにする。
.md は HTML から直接リンクされたもの（配布用の手引きなど）だけ出す。.json・.yaml などは出さない。

使い方: python3 scripts/pages_collect_public.py docs _site/docs
"""
from __future__ import annotations

import re
import shutil
import sys
from pathlib import Path
from urllib.parse import unquote, urlsplit

REF_RE = re.compile(r"""(?:src|href|poster|data-src)\s*=\s*["']([^"'#?]+)""", re.I)
CSS_URL_RE = re.compile(r"""url\(\s*["']?([^"')#?]+)""", re.I)
NEVER = {".json", ".yaml", ".yml", ".txt", ".csv", ".py", ".sh", ".env", ".log", ".xlsx", ".docx"}
# HTML からリンクされていても内部向けのもの（コマンド・パス・鍵の名前が並ぶ）
DENY_NAMES = {"運用コマンド一覧.md"}
SCAN = {".html", ".htm", ".css"}


def refs(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8", errors="ignore")
    out = REF_RE.findall(text) if path.suffix.lower() in {".html", ".htm"} else []
    out += CSS_URL_RE.findall(text)
    return out


def collect(src: Path) -> set[Path]:
    src = src.resolve()
    todo = [p.resolve() for p in src.rglob("*") if p.suffix.lower() in {".html", ".htm"} and p.is_file()]
    seen: set[Path] = set()
    while todo:
        p = todo.pop()
        if p in seen:
            continue
        seen.add(p)
        if p.suffix.lower() not in SCAN:
            continue
        for raw in refs(p):
            u = urlsplit(raw.strip())
            if u.scheme or u.netloc or raw.startswith(("/", "data:", "mailto:", "javascript:")):
                continue
            target = (p.parent / unquote(u.path)).resolve()
            if not target.is_file() or src not in target.parents:
                continue
            if target.suffix.lower() in NEVER or target.name.startswith(".") or target.name in DENY_NAMES:
                continue
            todo.append(target)
    return seen


def main(argv: list[str]) -> int:
    src, dst = Path(argv[1]), Path(argv[2])
    files = collect(src)
    for f in sorted(files):
        rel = f.relative_to(src.resolve())
        out = dst / rel
        out.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(f, out)
    print(f"pages: {len(files)} files from {src}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
