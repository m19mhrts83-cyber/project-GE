#!/usr/bin/env python3
"""
PDF to Markdown 変換スクリプト
PDFファイルからテキストを抽出し、Markdown形式で保存する。

使い方:
    python3 pdf_to_md.py input.pdf
    python3 pdf_to_md.py input.pdf -o ~/Downloads/
"""

import argparse
import os
import sys

import pdfplumber


def table_to_markdown(table: list[list]) -> str:
    """テーブルデータをMarkdownテーブル形式に変換する"""
    if not table or len(table) < 1:
        return ""

    # セル内のNoneを空文字に置換
    cleaned = []
    for row in table:
        cleaned.append([str(cell) if cell is not None else "" for cell in row])

    # 最大列数を取得
    max_cols = max(len(row) for row in cleaned)

    # 列数を揃える
    for row in cleaned:
        while len(row) < max_cols:
            row.append("")

    lines = []

    # ヘッダー行
    header = cleaned[0]
    lines.append("| " + " | ".join(header) + " |")

    # 区切り行
    lines.append("| " + " | ".join(["---"] * max_cols) + " |")

    # データ行
    for row in cleaned[1:]:
        lines.append("| " + " | ".join(row) + " |")

    return "\n".join(lines)


def extract_page_text(page) -> str:
    """ページからテキストとテーブルを抽出する"""
    parts = []

    # テーブルを検出
    tables = page.find_tables()

    if tables:
        # テーブルがある場合、テーブル領域とそれ以外のテキストを分けて処理
        table_bboxes = [table.bbox for table in tables]

        # テーブル外のテキストを取得
        text_outside_tables = page.filter(
            lambda obj: not any(
                obj.get("x0", 0) >= bbox[0] - 1
                and obj.get("top", 0) >= bbox[1] - 1
                and obj.get("x1", 0) <= bbox[2] + 1
                and obj.get("bottom", 0) <= bbox[3] + 1
                for bbox in table_bboxes
            )
        ).extract_text()

        if text_outside_tables:
            parts.append(text_outside_tables)

        # テーブルをMarkdown形式に変換
        for table in tables:
            table_data = table.extract()
            md_table = table_to_markdown(table_data)
            if md_table:
                parts.append("\n" + md_table + "\n")
    else:
        # テーブルがない場合は全テキストを取得
        text = page.extract_text()
        if text:
            parts.append(text)

    return "\n".join(parts) if parts else ""


def pdf_to_markdown(pdf_path: str, output_path: str) -> str:
    """PDFファイルをMarkdownに変換して保存する"""
    if not os.path.exists(pdf_path):
        print(f"エラー: ファイルが見つかりません: {pdf_path}", file=sys.stderr)
        sys.exit(1)

    md_parts = []

    # PDFファイル名をタイトルとして追加
    pdf_name = os.path.splitext(os.path.basename(pdf_path))[0]
    md_parts.append(f"# {pdf_name}\n")

    with pdfplumber.open(pdf_path) as pdf:
        total_pages = len(pdf.pages)
        print(f"処理中: {pdf_path} ({total_pages}ページ)")

        for i, page in enumerate(pdf.pages, start=1):
            md_parts.append(f"## Page {i}\n")
            text = extract_page_text(page)
            if text:
                md_parts.append(text)
            else:
                md_parts.append("*(このページにはテキストが含まれていません)*")
            md_parts.append("")  # 空行で区切り

    md_content = "\n".join(md_parts)

    # ファイルに書き出し
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(md_content)

    print(f"変換完了: {output_path}")
    return output_path


def main():
    parser = argparse.ArgumentParser(
        description="PDFファイルをMarkdown(.md)に変換するツール"
    )
    parser.add_argument(
        "pdf_path",
        help="変換するPDFファイルのパス",
    )
    parser.add_argument(
        "-o",
        "--output-dir",
        help="出力先ディレクトリ（省略時はPDFと同じディレクトリ）",
        default=None,
    )

    args = parser.parse_args()

    # PDFパスを絶対パスに変換
    pdf_path = os.path.abspath(os.path.expanduser(args.pdf_path))

    # 出力パスを決定
    pdf_basename = os.path.splitext(os.path.basename(pdf_path))[0]
    md_filename = f"{pdf_basename}.md"

    if args.output_dir:
        output_dir = os.path.abspath(os.path.expanduser(args.output_dir))
        os.makedirs(output_dir, exist_ok=True)
        output_path = os.path.join(output_dir, md_filename)
    else:
        output_path = os.path.join(os.path.dirname(pdf_path), md_filename)

    pdf_to_markdown(pdf_path, output_path)


if __name__ == "__main__":
    main()
