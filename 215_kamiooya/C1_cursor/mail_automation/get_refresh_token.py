#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
REFRESH_TOKENを取得するスクリプト

このスクリプトは、既存のtoken.pickleファイルから
REFRESH_TOKENを抽出して表示します。
"""

import pickle
import sys
from pathlib import Path

def get_refresh_token():
    """token.pickleからREFRESH_TOKENを取得する"""
    
    script_dir = Path(__file__).parent
    token_file = script_dir / 'token.pickle'
    
    if not token_file.exists():
        print("❌ エラー: token.pickle ファイルが見つかりません")
        print(f"   期待されるパス: {token_file}")
        print("\n💡 ヒント:")
        print("   send_mail.py を一度実行してGmail認証を完了してください。")
        return None
    
    try:
        with open(token_file, 'rb') as f:
            creds = pickle.load(f)
        
        if hasattr(creds, 'refresh_token') and creds.refresh_token:
            print("✅ REFRESH_TOKENを取得しました！")
            print("\n" + "=" * 70)
            print("以下のREFRESH_TOKENをコピーしてください:")
            print("=" * 70)
            print(creds.refresh_token)
            print("=" * 70)
            print("\n📝 次の手順:")
            print("1. 上記のREFRESH_TOKENをコピー")
            print("2. ~/.cursor/mcp.json を開く")
            print("3. 'YOUR_REFRESH_TOKEN_HERE' を実際のトークンに置き換える")
            print("4. Cursorを再起動")
            return creds.refresh_token
        else:
            print("❌ エラー: REFRESH_TOKENが見つかりません")
            print("\n💡 ヒント:")
            print("   token.pickleを削除して、send_mail.pyを再実行してください。")
            return None
            
    except Exception as e:
        print(f"❌ エラーが発生しました: {e}")
        return None

if __name__ == '__main__':
    get_refresh_token()
