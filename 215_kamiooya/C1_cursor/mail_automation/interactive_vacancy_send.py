#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
空室対策メール送信用の対話型ラッパースクリプト

目的:
- 毎回のコマンドを覚えなくても、
  1) 管理会社一覧Excelの確認
  2) 送信に使うMDファイルの指定
  を対話形式で行ったうえで、既存の send_mail.py を呼び出して送信する。

使い方（例）:
  （推奨）git-repos 側の venv から実行
  cd /Users/matsunomasaharu/git-repos/ProgramCode
  ./venv_gmail/bin/python "/Users/matsunomasaharu/Library/CloudStorage/OneDrive-個人用/215_神・大家さん倶楽部/C1_cursor/mail_automation/interactive_vacancy_send.py"
"""

import sys
import subprocess
from pathlib import Path


SCRIPT_DIR = Path(__file__).parent

# 215_神・大家さん倶楽部 のルートディレクトリ（データ・プログラム本体の置き場）
ROOT_DIR = SCRIPT_DIR.parents[1]

# デフォルトで使用する管理会社一覧Excelとシート名（G2）
DEFAULT_EXCEL = ROOT_DIR / "20_【空室対策】【修繕】【売却】" / "21_【空室対策】募集,ステージング,物件管理" / "★管理会社一覧.xlsx"
DEFAULT_SHEET_NAME = "G2"


def ask_confirm_excel() -> bool:
    """管理会社一覧Excelの確認を行う。"""
    print("=" * 70)
    print("📊 管理会社一覧の確認")
    print("=" * 70)
    print("現在の管理会社一覧として、次のExcelを使用します。")
    print(f"  Excelファイル : {DEFAULT_EXCEL}")
    print(f"  シート名       : {DEFAULT_SHEET_NAME}")
    if not DEFAULT_EXCEL.exists():
        print("\n⚠️  上記のExcelファイルが見つかりません。パスを確認してください。")
        return False

    ans = input("\nこの管理会社一覧で送信してよろしいですか？ (y/N): ").strip().lower()
    return ans in ("y", "yes")


def resolve_md_path(raw_input: str) -> Path:
    """
    ユーザー入力からMDファイルのパスを解決する。

    想定する入力例:
      @215_神・大家さん倶楽部/C2_ルーティン作業/24_空室対策メール履歴/260313_G1_空室対策.md
    """
    text = raw_input.strip()

    # 先頭の @ はカーソルでの指定記法なので取り除く
    if text.startswith("@"):
        text = text[1:].strip()

    p = Path(text)

    # 絶対パスがそのまま存在する場合
    if p.is_absolute() and p.exists():
        return p

    # 215_神・大家さん倶楽部 から始まる相対パスとして扱う
    candidate = ROOT_DIR.parent / text
    if candidate.exists():
        return candidate

    # ROOT_DIR からの相対パスとしても試す
    candidate2 = ROOT_DIR / text
    if candidate2.exists():
        return candidate2

    raise FileNotFoundError(f"MDファイルが見つかりませんでした: {raw_input}")


def ask_md_file() -> Path:
    """送信に使用するMDファイルのパスを対話的に指定させる。"""
    print("\n" + "=" * 70)
    print("📄 送信するMDファイルの指定")
    print("=" * 70)
    print("送信に使用するMDファイルを指定してください。")
    print("例:")
    print("  @215_神・大家さん倶楽部/C2_ルーティン作業/24_空室対策メール履歴/260313_G1_空室対策.md")
    print("  または、絶対パス / 相対パスでも構いません。")

    raw = input("\nMDファイルパス: ").strip()
    if not raw:
        raise ValueError("MDファイルが指定されていません。")

    md_path = resolve_md_path(raw)
    print(f"\n✓ 使用するMDファイル: {md_path}")
    return md_path


def run_send_mail(md_path: Path) -> int:
    """send_mail.py を呼び出して実際の送信を行う。"""
    send_mail_py = SCRIPT_DIR / "send_mail.py"
    if not send_mail_py.exists():
        print(f"エラー: send_mail.py が見つかりません: {send_mail_py}")
        return 1

    cmd = [
        sys.executable,
        str(send_mail_py),
        "--md-file",
        str(md_path),
        "--excel-file",
        str(DEFAULT_EXCEL),
        "--sheet-name",
        DEFAULT_SHEET_NAME,
        "--yes",  # send_mail.py 側の送信確認はスキップ（このラッパー側で確認済み）
    ]

    print("\n" + "=" * 70)
    print("🚀 send_mail.py を実行してメール送信を開始します")
    print("=" * 70)
    print("実行コマンド:")
    print("  " + " ".join(cmd))
    print()

    result = subprocess.run(cmd)
    return result.returncode


def main():
    # 1. 管理会社一覧の確認
    if not ask_confirm_excel():
        print("\n送信をキャンセルしました（管理会社一覧の確認でNoが選択されました）。")
        sys.exit(0)

    # 2. 送信するMDファイルの指定
    try:
        md_path = ask_md_file()
    except Exception as e:
        print(f"\nエラー: {e}")
        sys.exit(1)

    # 3. send_mail.py で送信実行
    code = run_send_mail(md_path)
    if code != 0:
        print(f"\nエラー: send_mail.py の実行が終了コード {code} で失敗しました。")
        sys.exit(code)

    print("\n✅ 対話型コマンドでのメール送信が完了しました。")


if __name__ == "__main__":
    main()

