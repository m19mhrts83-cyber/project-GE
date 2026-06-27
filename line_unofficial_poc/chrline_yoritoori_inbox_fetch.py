#!/usr/bin/env python3
"""
パートナー取り込み向け: LINE sync + オープンチャットを 1 プロセス・1 回の認証で実行する。

目的:
  - やり取り確認1回につき QR 再認証を最大1回に抑える（sync と open-chat を別プロセスで走らせない）
  - thread MID 候補の dry-run も同一セッション内で実行可能

使い方（パートナー確認の LINE / オプチャ同期）:
  cd ~/git-repos/line_unofficial_poc
  .venv/bin/python chrline_yoritoori_inbox_fetch.py --allow-qr-login

個別のみ:
  --skip-open-chat / --skip-sync
"""
from __future__ import annotations

import argparse
import sys

from chrline_client_utils import build_logged_in_client, save_root_from_env

import chrline_open_chat_to_md as open_chat_mod
import chrline_sync_to_yoritoori as sync_mod
from chrline_line_health import run_line_health_routine


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="LINE sync + オープンチャットを1回のQR認証でまとめて実行",
    )
    parser.add_argument(
        "--allow-qr-login",
        action="store_true",
        help="保存トークン無効時に QR 再認証を許可（このスクリプト全体で1回だけ）",
    )
    parser.add_argument("--skip-sync", action="store_true", help="chrline_sync_to_yoritoori をスキップ")
    parser.add_argument("--skip-open-chat", action="store_true", help="chrline_open_chat_to_md をスキップ")
    parser.add_argument(
        "--discover-thread-mids-dry-run",
        action="store_true",
        help="オープンチャット同期後に thread MID 候補を --discover-thread-mids --dry-run で確認",
    )
    parser.add_argument(
        "--discover-init",
        action="store_true",
        help="discover 時に --init を付与（履歴スキャン。初回 bootstrap 向け）",
    )
    parser.add_argument(
        "--discover-min-hit-count",
        type=int,
        default=1,
        help="discover の --min-hit-count（既定 1）",
    )
    parser.add_argument(
        "--sync-preset",
        default="line-default",
        choices=("line-default", "tcell-both", "tcell-yuki", "leaf-grandole", "none"),
        help="sync 側の --preset（既定: line-default）",
    )
    parser.add_argument(
        "--line-health",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="sync 後に LINE 本文ヘルス要約を出力（既定: 有効）",
    )
    parser.add_argument(
        "--line-health-since-days",
        type=int,
        default=7,
        help="ヘルス要約の decode_stats 集計日数（既定 7）",
    )
    parser.add_argument(
        "--skip-sync-improved-params",
        action="store_true",
        help="sync に案D改善パラメータ（backfill 300 / fetch-depth 1500 等）を付けない",
    )
    return parser


def _build_sync_argv(preset: str, *, improved: bool) -> list[str]:
    argv = ["--preset", preset]
    if improved:
        argv.extend(
            [
                "--direct-backfill-count",
                "300",
                "--retry-fetch-count",
                "300",
                "--fetch-depth",
                "1500",
                "--retry-max-attempts",
                "12",
                "--retry-interval-sec",
                "30",
            ]
        )
    return argv


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    if args.skip_sync and args.skip_open_chat:
        print("エラー: --skip-sync と --skip-open-chat を同時に指定できません。", file=sys.stderr)
        return 1

    save_root = save_root_from_env()
    cl = build_logged_in_client(save_root, allow_qr_login=bool(args.allow_qr_login))

    exit_code = 0
    if not args.skip_sync:
        sync_argv = _build_sync_argv(
            args.sync_preset,
            improved=not args.skip_sync_improved_params,
        )
        sync_args = sync_mod.build_arg_parser().parse_args(sync_argv)
        rc = sync_mod.run(sync_args, client=cl)
        if rc != 0:
            exit_code = rc

        if args.line_health and rc == 0:
            try:
                _inv, health_block = run_line_health_routine(
                    since_days=int(args.line_health_since_days),
                    save_baseline=True,
                    save_root=save_root,
                )
                print(health_block, flush=True)
            except Exception as e:
                print(f"# LINE本文ヘルス: スキップ（{type(e).__name__}: {e}）", file=sys.stderr)

    if not args.skip_open_chat:
        # メイン差分とスレッド専用差分を分離（503 スレッド全走査による 401 連発を抑える）
        open_args_main = open_chat_mod.build_arg_parser().parse_args(["--no-threads"])
        rc = open_chat_mod.run(open_args_main, client=cl)
        if rc != 0 and exit_code == 0:
            exit_code = rc

        if args.discover_thread_mids_dry_run:
            discover_argv = ["--discover-thread-mids", "--dry-run", "--no-threads"]
            if args.discover_init:
                discover_argv.append("--init")
                discover_argv.append("--max-pages-per-stream=50")
            if args.discover_min_hit_count > 1:
                discover_argv.extend(["--min-hit-count", str(args.discover_min_hit_count)])
            discover_args = open_chat_mod.build_arg_parser().parse_args(discover_argv)
            drc = open_chat_mod.run(discover_args, client=cl)
            if drc != 0 and exit_code == 0:
                exit_code = drc

        open_args_threads = open_chat_mod.build_arg_parser().parse_args(["--threads-only"])
        rc2 = open_chat_mod.run(open_args_threads, client=cl)
        if rc2 != 0 and exit_code == 0:
            exit_code = rc2

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
