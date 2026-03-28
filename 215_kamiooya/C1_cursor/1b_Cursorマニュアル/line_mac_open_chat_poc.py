#!/usr/bin/env python3
"""
LINE for Mac を前面にし、指定文字列をキー入力する PoC（UI はバージョンで大きく変わる想定）。

- アクセシビリティと自動化の許可が必要（システム設定 → プライバシーとセキュリティ）。
- 送信（Enter）は行わない。誤チャット防止のため、トークが開いたかは必ず目視確認すること。

動作確認メモ欄: README（000_共通）に LINE Mac のバージョンを追記するとよい。

使い方:
  python line_mac_open_chat_poc.py --title "グループ表示名の一部"
  python line_mac_open_chat_poc.py --title "○○" --dry-run
"""

from __future__ import annotations

import argparse
import subprocess
import sys


def run_applescript(script: str) -> tuple[int, str, str]:
    r = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=60)
    return r.returncode, (r.stdout or "").strip(), (r.stderr or "").strip()


def escape_for_apple_string(s: str) -> str:
    return s.replace("\\", "\\\\").replace('"', '\\"')


def pbpaste() -> str:
    r = subprocess.run(["pbpaste"], capture_output=True, text=True, timeout=10)
    return r.stdout if r.returncode == 0 else ""


def pbcopy(text: str) -> None:
    subprocess.run(["pbcopy"], input=text, text=True, timeout=10)


def main() -> None:
    p = argparse.ArgumentParser(description="LINE Mac 前面化＋タイトル入力 PoC")
    p.add_argument("--title", required=True, help="トーク一覧検索や入力に使う文字列")
    p.add_argument("--dry-run", action="store_true", help="osascript を実行せず内容のみ表示")
    args = p.parse_args()
    title = args.title.strip()
    if not title:
        print("エラー: --title が空です。", file=sys.stderr)
        sys.exit(1)

    if sys.platform != "darwin":
        print("エラー: macOS のみです。", file=sys.stderr)
        sys.exit(1)

    t = escape_for_apple_string(title)

    # LINE を起動・前面化後、Unicode テキストをペーストで送る（日本語の keystroke 問題を避ける）
    script = f'''
    tell application "LINE" to activate
    delay 0.6
    set the clipboard to "{t}"
    tell application "System Events"
      tell process "LINE"
        set frontmost to true
        delay 0.2
        keystroke "f" using {{command down}}
        delay 0.3
        keystroke "a" using {{command down}}
        delay 0.1
        keystroke "v" using {{command down}}
        delay 0.2
      end tell
    end tell
    '''

    if args.dry_run:
        print("【dry-run】実行する AppleScript（概略）:")
        print("  1) LINE を activate")
        print("  2) 一時的にクリップボードへ --title を載せ、Cmd+F → Cmd+A → Cmd+V")
        print("  3) Python 側で直前のクリップボード文字列を復元（プレーンテキストのみ）")
        print("")
        print("※ Cmd+F が別機能に割り当てられている版では動きません。動かないときはスクリプトを手で直してください。")
        return

    clip_backup = pbpaste()
    code, out, err = -1, "", ""
    try:
        code, out, err = run_applescript(script)
    finally:
        try:
            pbcopy(clip_backup)
        except OSError:
            pass
    if code != 0:
        print(f"osascript 失敗 (exit {code})", file=sys.stderr)
        if err:
            print(err, file=sys.stderr)
        sys.exit(1)
    if out:
        print(out)
    print("実行しました。LINE のウィンドウで該当トークが絞り込まれたか確認してください（送信はしていません）。")


if __name__ == "__main__":
    main()
