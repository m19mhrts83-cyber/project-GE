#!/usr/bin/env python3
"""
LINEオープンチャットのスレッド返信を、手動コピー経由で 5.やり取り.md に追記する補助スクリプト。

背景:
- 一部環境では OpenChat スレッド本文を API で安定取得できないため、
  LINE Mac でスレッド本文をコピーして履歴へ反映する半自動フローを提供する。

使い方:
  # 1) LINE Mac で対象スレッド本文をコピー（Cmd+C）
  # 2) 追記
  python line_open_chat_thread_clip_to_yoritoori.py --chat 31修繕

  # ファイル入力でも可
  python line_open_chat_thread_clip_to_yoritoori.py --chat 31修繕 --text-file ~/Desktop/thread.txt
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ChatTarget:
    folder: str
    display_name: str
    group_label: str


TARGETS: dict[str, ChatTarget] = {
    "31修繕": ChatTarget(
        folder="815_神大家オプチャ/31修繕相談G",
        display_name="31修繕相談G【神大家】",
        group_label="31修繕相談G【神大家】 スレッド補完",
    ),
    "33融資": ChatTarget(
        folder="815_神大家オプチャ/33融資相談G",
        display_name="33融資相談G【神大家】",
        group_label="33融資相談G【神大家】 スレッド補完",
    ),
    "30空室": ChatTarget(
        folder="815_神大家オプチャ/30空室相談G",
        display_name="30空室相談G【神大家】",
        group_label="30空室相談G【神大家】 スレッド補完",
    ),
    "12東海北陸": ChatTarget(
        folder="815_神大家オプチャ/12東海北陸G",
        display_name="12東海北陸G【神大家】",
        group_label="12東海北陸G【神大家】 スレッド補完",
    ),
}


def read_clipboard() -> str:
    if sys.platform != "darwin":
        raise RuntimeError("クリップボード読み取りは macOS のみ対応です。--text-file を使ってください。")
    r = subprocess.run(["pbpaste"], capture_output=True, text=True, timeout=10)
    if r.returncode != 0:
        raise RuntimeError("pbpaste の実行に失敗しました。")
    return r.stdout or ""


def normalize_body(text: str) -> str:
    body = (text or "").strip()
    if not body:
        return ""
    header = "[LINEオープンチャット手動補完]\n[種別] スレッド返信"
    return f"{header}\n\n{body}\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="LINEオープンチャットのスレッド本文を手動補完で追記")
    parser.add_argument("--chat", required=True, choices=sorted(TARGETS.keys()), help="追記先チャット")
    parser.add_argument("--text-file", help="本文ファイル（未指定時はクリップボード）")
    parser.add_argument("--direction", choices=("receive", "send"), default="receive", help="受信 or 送信")
    parser.add_argument("--dry-run", action="store_true", help="追記せずコマンドのみ表示")
    parser.add_argument("--no-dedup", action="store_true", help="重複検知を無効化")
    args = parser.parse_args()

    target = TARGETS[args.chat]
    if args.text_file:
        p = Path(args.text_file).expanduser()
        if not p.is_file():
            print(f"エラー: ファイルが見つかりません: {p}", file=sys.stderr)
            return 1
        src_text = p.read_text(encoding="utf-8")
    else:
        try:
            src_text = read_clipboard()
        except RuntimeError as e:
            print(f"エラー: {e}", file=sys.stderr)
            return 1

    body = normalize_body(src_text)
    if not body.strip():
        print("エラー: 本文が空です。LINEで本文をコピーしてください。", file=sys.stderr)
        return 1

    script_dir = Path(__file__).resolve().parent
    sink_script = script_dir / "line_to_yoritoori_clip.py"
    if not sink_script.is_file():
        print(f"エラー: 連携スクリプトが見つかりません: {sink_script}", file=sys.stderr)
        return 1

    with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".txt", delete=True) as tf:
        tf.write(body)
        tf.flush()

        cmd = [
            sys.executable,
            str(sink_script),
            "--folder",
            target.folder,
            "--display-name",
            target.display_name,
            "--group",
            "--group-label",
            target.group_label,
            "--direction",
            args.direction,
            "--text-file",
            tf.name,
        ]
        if args.no_dedup:
            cmd.append("--no-dedup")

        if args.dry_run:
            print("dry-run: 実行コマンド")
            print(" ".join(cmd))
            print("")
            print("本文プレビュー:")
            print(body[:300] + ("..." if len(body) > 300 else ""))
            return 0

        r = subprocess.run(cmd, text=True)
        return int(r.returncode or 0)


if __name__ == "__main__":
    raise SystemExit(main())
