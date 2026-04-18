#!/usr/bin/env python3
"""main.pdf を PNG にラスタライズし、NotebookLM 図解 HTML の Main スライドを更新する。

使い方（リポジトリルートから）:
  ProgramCode/venv/bin/python docs/tools/convert_nb_comm_main_pdf.py

前提: PyMuPDF（`pip install pymupdf`）
入力: docs/assets/nb_comm_unification/main.pdf
出力:
  - docs/assets/nb_comm_unification/main-01.png …（ゼロ埋め2桁）
  - DX互助会向け_コミュニケーション一元化_NotebookLM図解.html 内
    <!-- NB_COMM_MAIN_SLIDES_START --> … <!-- NB_COMM_MAIN_SLIDES_END --> を置換
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

try:
    import fitz  # PyMuPDF
except ImportError:
    print("PyMuPDF が必要です: ProgramCode/venv/bin/pip install pymupdf", file=sys.stderr)
    sys.exit(1)

HERE = Path(__file__).resolve().parent
DOCS = HERE.parent
ASSETS = DOCS / "assets" / "nb_comm_unification"
PDF_PATH = ASSETS / "main.pdf"
HTML_PATH = DOCS / "DX互助会向け_コミュニケーション一元化_NotebookLM図解.html"
TARGET_WIDTH = 1920

START_MARK = "<!-- NB_COMM_MAIN_SLIDES_START -->"
END_MARK = "<!-- NB_COMM_MAIN_SLIDES_END -->"


def build_main_slides_block(n: int, img_w: int, img_h: int) -> str:
    lines: list[str] = [START_MARK]
    pdf_rel = "assets/nb_comm_unification/main.pdf"
    for i in range(1, n + 1):
        sid = f"s-m{i:02d}"
        label = f"Main {i}/{n}"
        aria_n = i + 1
        lines.append(
            f'    <section class="slide" id="{sid}" data-label="{label}" '
            f'aria-label="スライド{aria_n} Main {i}/{n}">'
        )
        lines.append(f"      <h2>Main 資料（{i} / {n}）</h2>")
        lines.append(
            f'      <img src="assets/nb_comm_unification/main-{i:02d}.png" '
            f'alt="Main 資料 {i} ページ目" width="{img_w}" height="{img_h}" loading="lazy">'
        )
        if i == 1:
            lines.append(
                "      <p class=\"pdf-note\">印刷・オフライン用: "
                f'<a href="{pdf_rel}" target="_blank" rel="noopener noreferrer">'
                "main.pdf を別タブで開く</a> ／ "
                f'<a href="{pdf_rel}" download>ダウンロード</a></p>'
            )
        lines.append("    </section>")
    lines.append(f"    {END_MARK}")
    return "\n".join(lines) + "\n"


def patch_html(html: str, new_block: str) -> str:
    pattern = re.compile(
        re.escape(START_MARK) + r".*?" + re.escape(END_MARK),
        re.DOTALL,
    )
    if not pattern.search(html):
        print(f"HTML にマーカーがありません: {HTML_PATH}", file=sys.stderr)
        sys.exit(1)
    return pattern.sub(new_block.rstrip("\n"), html, count=1)


def main() -> int:
    if not PDF_PATH.is_file():
        print(f"見つかりません: {PDF_PATH}", file=sys.stderr)
        return 1
    if not HTML_PATH.is_file():
        print(f"見つかりません: {HTML_PATH}", file=sys.stderr)
        return 1

    doc = fitz.open(PDF_PATH)
    n = doc.page_count
    for p in ASSETS.glob("main-[0-9][0-9].png"):
        p.unlink()

    img_w, img_h = TARGET_WIDTH, 1072
    for i in range(n):
        page = doc[i]
        w = page.rect.width
        if w <= 0:
            continue
        scale = TARGET_WIDTH / w
        mat = fitz.Matrix(scale, scale)
        pix = page.get_pixmap(matrix=mat, alpha=False)
        out = ASSETS / f"main-{i + 1:02d}.png"
        pix.save(out.as_posix())
        img_w, img_h = pix.width, pix.height
        print(out.name, img_w, "x", img_h)

    doc.close()

    new_block = build_main_slides_block(n, img_w, img_h)
    old_html = HTML_PATH.read_text(encoding="utf-8")
    HTML_PATH.write_text(patch_html(old_html, new_block), encoding="utf-8")
    print(f"OK: {n} ページ PNG + HTML Main ブロック更新 → {HTML_PATH.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
