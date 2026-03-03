#!/bin/bash
# 260214_G2_空室対策メールをG2シート宛に送信（自動承認）
# ダブルクリックで実行（Mac の「ターミナル」が開いて実行される）
DIR="/Users/matsunomasaharu/Library/CloudStorage/OneDrive-個人用/215_神・大家さん倶楽部/C1_cursor/mail_automation"
MD_FILE="/Users/matsunomasaharu/Library/CloudStorage/OneDrive-個人用/215_神・大家さん倶楽部/C2_ルーティン作業/24_空室対策メール履歴/260214_G2_空室対策.md"
EXCEL_FILE="/Users/matsunomasaharu/Library/CloudStorage/OneDrive-個人用/215_神・大家さん倶楽部/20_【空室対策】【修繕】【売却】/21_【空室対策】募集,ステージング,物件管理/★管理会社一覧.xlsx"

cd "$DIR" || exit 1
PYTHONINSPECT= "$DIR/venv/bin/python" -c "
import sys
sys.argv = ['send_mail.py', '--md-file', \"$MD_FILE\", '--excel-file', \"$EXCEL_FILE\", '--sheet-name', 'G2', '--email-column', 'mail', '--yes']
with open(\"$DIR/send_mail.py\", encoding='utf-8') as f:
    code = compile(f.read(), 'send_mail.py', 'exec')
    g = {'__name__': '__main__', '__file__': \"$DIR/send_mail.py\", '__builtins__': __builtins__}
    exec(code, g)
"
echo ""
echo "Enter キーを押すとこのウィンドウを閉じます..."
read
