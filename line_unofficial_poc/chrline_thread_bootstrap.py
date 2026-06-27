#!/usr/bin/env python3
"""
815 オープンチャットのスレッド専用タイムライン初回セットアップ。

手順（1 回の QR 認証）:
  1. メイン履歴から thread MID 候補を discover（--discover-only --init）
  2. （任意）YAML に thread_mids 追記
  3. （任意）未参加スレッドへ join
  4. スレッドのみバックフィル（--init --no-main）

例:
  cd ~/git-repos/line_unofficial_poc
  .venv/bin/python chrline_thread_bootstrap.py --allow-qr-login --discover-only
  .venv/bin/python chrline_thread_bootstrap.py --allow-qr-login --append-yaml --join-threads
  .venv/bin/python chrline_thread_bootstrap.py --allow-qr-login --backfill
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from chrline_client_utils import build_logged_in_client, save_root_from_env

import chrline_open_chat_to_md as open_chat_mod


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="オープンチャット・スレッド初回ブートストラップ")
    p.add_argument("--allow-qr-login", action="store_true", help="QR 再認証を許可")
    p.add_argument(
        "--discover-only",
        action="store_true",
        help="メイン履歴スキャンのみ（候補レポート）",
    )
    p.add_argument(
        "--append-yaml",
        action="store_true",
        help="discover 後に open_chat_routes.yaml へ thread_mids を追記",
    )
    p.add_argument(
        "--join-threads",
        action="store_true",
        help="未参加スレッドを対話確認して join",
    )
    p.add_argument(
        "--join-threads-confirm-file",
        type=Path,
        default=None,
        metavar="PATH",
        help="参加許可 MID 一覧（1行1件）",
    )
    p.add_argument(
        "--join-threads-yes",
        action="store_true",
        help="未参加スレッドを確認なしで join（非推奨）",
    )
    p.add_argument(
        "--backfill",
        action="store_true",
        help="thread_mids のスレッド専用タイムラインを --init でバックフィル",
    )
    p.add_argument(
        "--max-pages-per-stream",
        type=int,
        default=100,
        help="discover / backfill の最大ページ数",
    )
    p.add_argument(
        "--min-hit-count",
        type=int,
        default=1,
        help="discover で YAML 追記する最小ヒット数",
    )
    p.add_argument(
        "--full",
        action="store_true",
        help="discover → append-yaml → join-threads → backfill を一括実行",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    if args.full:
        args.discover_only = True
        args.append_yaml = True
        args.join_threads = True
        args.backfill = True

    if not any((args.discover_only, args.append_yaml, args.join_threads, args.backfill, args.full)):
        print(
            "エラー: --discover-only / --append-yaml / --join-threads / --backfill / --full のいずれかを指定してください。",
            file=sys.stderr,
        )
        return 1

    save_root = save_root_from_env()
    cl = build_logged_in_client(save_root, allow_qr_login=bool(args.allow_qr_login))
    exit_code = 0

    confirm_path = args.join_threads_confirm_file

    if args.discover_only or args.append_yaml:
        discover_argv = [
            "--discover-only",
            "--discover-from-yoritoori",
            f"--max-pages-per-stream={args.max_pages_per_stream}",
            f"--min-hit-count={args.min_hit_count}",
        ]
        if args.append_yaml:
            discover_argv.append("--auto-append-thread-mids")
        rc = open_chat_mod.run(
            open_chat_mod.build_arg_parser().parse_args(discover_argv),
            client=cl,
        )
        if rc != 0:
            exit_code = rc

    if args.join_threads or args.join_threads_yes or confirm_path:
        join_argv = ["--no-main", "--dry-run", "--max-pages-per-stream=1"]
        if args.join_threads:
            join_argv.append("--join-threads")
        if args.join_threads_yes:
            join_argv.append("--join-threads-yes")
        if confirm_path:
            join_argv.extend(["--join-threads-confirm-file", str(confirm_path)])
        rc = open_chat_mod.run(
            open_chat_mod.build_arg_parser().parse_args(join_argv),
            client=cl,
        )
        if rc != 0 and exit_code == 0:
            exit_code = rc

    if args.backfill:
        back_argv = [
            "--init",
            "--no-main",
            f"--max-pages-per-stream={args.max_pages_per_stream}",
        ]
        if args.join_threads or args.join_threads_yes or confirm_path:
            if args.join_threads:
                back_argv.append("--join-threads")
            if args.join_threads_yes:
                back_argv.append("--join-threads-yes")
            if confirm_path:
                back_argv.extend(["--join-threads-confirm-file", str(confirm_path)])
        rc = open_chat_mod.run(
            open_chat_mod.build_arg_parser().parse_args(back_argv),
            client=cl,
        )
        if rc != 0 and exit_code == 0:
            exit_code = rc

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
