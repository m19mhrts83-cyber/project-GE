#!/usr/bin/env python3
"""
いけともAIニュースの「集」フォルダ（日付フォルダ）内の画像を OCR し、
1つの索引ファイル「画像テキスト索引.md」にまとめる。
検索すると、どの画像にその語が含まれるか分かる。

前提:
  - Tesseract インストール済み（brew install tesseract tesseract-lang）
  - pip install pytesseract Pillow 済み

使い方:
  python build_image_index.py                          # デフォルト保存先の直下にある集フォルダをすべて処理
  python build_image_index.py 20260201                 # 指定した集フォルダのみ処理
  python build_image_index.py --base /path/to/いけともAIニュース  # ベースパスを指定
"""

import argparse
import subprocess
import sys
from pathlib import Path

# デフォルト: いけともAIニュースのパス（gmail_ai_news_save と同じ）
SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_BASE = Path(
    "/Users/matsunomasaharu/Library/CloudStorage/GoogleDrive-m19m.hrts83@gmail.com"
    "/マイドライブ/DX互助会_共有フォルダ/05_knowledge/いけともAIニュース"
)

IMAGE_EXT = {".jpg", ".jpeg", ".png"}
INDEX_FILENAME = "画像テキスト索引.md"


def get_tesseract():
    try:
        import pytesseract
        from PIL import Image
        return pytesseract, Image
    except ImportError as e:
        print("エラー: pytesseract または Pillow がありません。", file=sys.stderr)
        print("  pip install pytesseract Pillow", file=sys.stderr)
        raise SystemExit(1) from e


def ocr_image(image_path, pytesseract, Image, lang="jpn+eng"):
    """1枚の画像からテキストを抽出。失敗時は空文字またはエラー文言を返す。"""
    try:
        img = Image.open(image_path)
        # 必要に応じて RGB に変換（PNG の RGBA など）
        if img.mode not in ("RGB", "L"):
            img = img.convert("RGB")
        text = pytesseract.image_to_string(img, lang=lang)
        return (text or "").strip()
    except Exception as e:
        return f"[OCR エラー: {e}]"


def collect_images(folder: Path):
    """フォルダ直下のサブフォルダをたどり、画像ファイルの相対パスを列挙（ソート済み）。"""
    collected = []
    for p in sorted(folder.rglob("*")):
        if p.is_file() and p.suffix.lower() in IMAGE_EXT:
            rel = p.relative_to(folder)
            collected.append(rel)
    return sorted(collected, key=lambda x: (str(x.parts[0]) if x.parts else "", x.name))


def build_index_for_folder(folder: Path, pytesseract, Image, dry_run: bool = False):
    """
    指定した「集」フォルダ（例: 20260201）内の画像を OCR し、
    そのフォルダ直下に 画像テキスト索引.md を1つ作成する。
    """
    folder = folder.resolve()
    if not folder.is_dir():
        print(f"スキップ（フォルダではありません）: {folder}")
        return 0

    images = collect_images(folder)
    if not images:
        print(f"スキップ（画像なし）: {folder}")
        return 0

    index_path = folder / INDEX_FILENAME
    lines = [
        f"# 画像テキスト索引 {folder.name}",
        "",
        "本文・図解画像から OCR で抽出したテキストです。キーワード検索で該当画像を探せます。",
        "",
        "---",
        "",
    ]

    for i, rel in enumerate(images):
        full = folder / rel
        rel_str = rel.as_posix()
        lines.append(f"## {rel_str}")
        lines.append("")
        if dry_run:
            lines.append("(dry-run)")
        else:
            text = ocr_image(full, pytesseract, Image)
            if text:
                lines.append(text)
            else:
                lines.append("(テキストなし)")
        lines.append("")
        lines.append("---")
        lines.append("")

    if not dry_run:
        index_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"作成: {index_path} （{len(images)} 枚）")
    return len(images)


def main():
    parser = argparse.ArgumentParser(description="いけともAIニュースの集フォルダ内画像を OCR し、1つの索引ファイルにまとめる")
    parser.add_argument(
        "folder",
        nargs="*",
        help="処理する集フォルダ名（例: 20260201）。省略時はベース直下の全フォルダを処理",
    )
    parser.add_argument(
        "--base",
        type=Path,
        default=DEFAULT_BASE,
        help="いけともAIニュースのベースパス",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="索引ファイルを書き出さずに処理内容だけ表示",
    )
    args = parser.parse_args()
    base = args.base.resolve()

    if not base.is_dir():
        print(f"エラー: ベースパスが存在しません: {base}", file=sys.stderr)
        sys.exit(1)

    pytesseract, Image = get_tesseract()

    # Tesseract が使えるか確認
    try:
        subprocess.run(
            ["tesseract", "--version"],
            capture_output=True,
            check=True,
            timeout=5,
        )
    except (FileNotFoundError, subprocess.CalledProcessError) as e:
        print("エラー: Tesseract がインストールされていないか、パスが通っていません。", file=sys.stderr)
        print("  macOS: brew install tesseract tesseract-lang", file=sys.stderr)
        sys.exit(1)

    if args.folder:
        # 指定されたフォルダ名のみ
        folders = [base / name for name in args.folder]
    else:
        # ベース直下のディレクトリのうち、数字6桁（日付）または 00_ で始まるもの
        folders = [p for p in sorted(base.iterdir()) if p.is_dir()]

    total = 0
    for folder in folders:
        n = build_index_for_folder(folder, pytesseract, Image, dry_run=args.dry_run)
        total += n

    print(f"\n合計: {total} 枚の画像を索引化しました。")


if __name__ == "__main__":
    main()
