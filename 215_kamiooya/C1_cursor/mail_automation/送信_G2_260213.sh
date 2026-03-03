#!/bin/bash
# 260213_G2_空室対策メールをG2シート宛に送信
# 対話モード（>>>）回避: python -c でスクリプトを読み込み実行（ファイルパスを渡さない）
set -e
DIR="/Users/matsunomasaharu/Library/CloudStorage/OneDrive-個人用/215_神・大家さん倶楽部/C1_cursor/mail_automation"
MD_FILE="/Users/matsunomasaharu/Library/CloudStorage/OneDrive-個人用/215_神・大家さん倶楽部/C2_ルーティン作業/24_空室対策メール履歴/260213_G2_空室対策.md"
EXCEL_FILE="/Users/matsunomasaharu/Library/CloudStorage/OneDrive-個人用/215_神・大家さん倶楽部/20_【空室対策】【修繕】【売却】/21_【空室対策】募集,ステージング,物件管理/★管理会社一覧.xlsx"

cd "$DIR"
# python -c で exec: スクリプトファイルを引数で渡さないため、対話モードの原因を回避
PYTHONINSPECT= "$DIR/venv/bin/python" -c "
import sys
sys.argv = ['send_mail.py', '--md-file', \"$MD_FILE\", '--excel-file', \"$EXCEL_FILE\", '--sheet-name', 'G2', '--email-column', 'mail', '--yes']
with open(\"$DIR/send_mail.py\", encoding='utf-8') as f:
    code = compile(f.read(), 'send_mail.py', 'exec')
    g = {'__name__': '__main__', '__file__': \"$DIR/send_mail.py\", '__builtins__': __builtins__}
    exec(code, g)
"
