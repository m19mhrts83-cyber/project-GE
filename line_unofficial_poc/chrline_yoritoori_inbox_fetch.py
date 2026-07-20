#!/usr/bin/env python3
"""
パートナー取り込み向け: LINE sync + オープンチャットを 1 プロセス・1 回の認証で実行する。

目的:
  - やり取り確認1回につき QR 再認証を **厳密に最大1回**（フェーズ間で第2 QR は出さない）
  - sync 後にセッションが死んだ場合は open-chat をスキップし、`--skip-sync` での別プロセス再実行を案内
  - thread MID 候補の dry-run も同一セッション内で実行可能
  - 既定は LINE sync → オープンチャットの順

使い方（パートナー確認の LINE / オプチャ同期・正本は Patch）:
  cd ~/git-repos/line_unofficial_poc
  ./run_patch.sh chrline_yoritoori_inbox_fetch.py --allow-qr-login --discover-thread-mids-dry-run

個別のみ:
  --skip-open-chat / --skip-sync
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

from chrline_client_utils import (
    build_logged_in_client,
    probe_square_session,
    recover_session_midrun,
    refresh_logged_in_client,
    refresh_square_logged_in_client,
    save_root_from_env,
)

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
        help="保存トークン無効時に QR 再認証を許可（プロセスあたり最大1回。切れてもフェーズ間で再QRしない）",
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
        "--open-chat-first",
        action="store_true",
        help="オプチャ → sync の順（既定は sync → オプチャ）",
    )
    parser.add_argument(
        "--skip-sync-improved-params",
        action="store_true",
        help="sync に案D改善パラメータ（backfill 300 / fetch-depth 1500 等）を付けない",
    )
    parser.add_argument(
        "--no-heal-degraded-threads",
        action="store_true",
        help="スレッド同期時の degraded heal を無効化（既定は有効）",
    )
    parser.add_argument(
        "--thread-catchup-pages",
        type=int,
        default=8,
        metavar="N",
        help="heal 対象スレッドの catchup ページ数（既定 8。復旧時は 10 推奨）",
    )
    parser.add_argument(
        "--force-open-chat",
        action="store_true",
        help="Square probe が 401 でもオープンチャット同期を強制（通常はスキップ）",
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


def _record_square_probe_state(detail: dict) -> None:
    """Phase 2: .jarvis_state/square_probe.json に probe 結果を追記。"""
    import json
    from datetime import datetime, timezone
    from pathlib import Path

    state_path = Path.home() / "git-repos" / ".jarvis_state" / "square_probe.json"
    try:
        state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.is_file() else {}
    except (json.JSONDecodeError, OSError):
        state = {}
    state["last_probe_at"] = datetime.now(timezone.utc).isoformat()
    state["last_probe"] = detail
    state["structural_limit"] = not bool(detail.get("ok"))
    hist = state.get("history") or []
    hist.append(detail)
    state["history"] = hist[-50:]
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _run_chrline_version_check_if_needed() -> None:
    """連携時: 新版ありのときだけバージョン報告ブロックを stdout に出す。"""
    try:
        repo_root = Path(__file__).resolve().parent.parent
        scripts_dir = str(repo_root / "scripts")
        if scripts_dir not in sys.path:
            sys.path.insert(0, scripts_dir)
        from jarvis_chrline_version_check import format_version_report, run_version_check

        result = run_version_check(force_upstream=False)
        if result.get("update_available") or result.get("source_refresh_suggested"):
            print(format_version_report(result), flush=True)
    except Exception as exc:
        print(f"# CHRLINE バージョン確認: スキップ（{type(exc).__name__}）", file=sys.stderr)


def _ensure_square_alive_no_qr(cl, save_root, *, phase: str):
    """フェーズ間の無 QR 再確認。復旧できなければ None。"""
    if cl is not None and probe_square_session(cl):
        return cl
    recovered = recover_session_midrun(save_root, cl, allow_qr_login=False)
    if recovered is not None and probe_square_session(recovered):
        return recovered
    print(
        f"# open-chat skipped: session_dead_after_{phase} no_second_qr"
        " （別プロセスで --skip-sync --allow-qr-login を検討）",
        file=sys.stderr,
    )
    return None


def _run_open_chat_phases(
    cl,
    *,
    save_root,
    allow_qr_login: bool,
    discover_thread_mids_dry_run: bool,
    discover_init: bool,
    discover_min_hit_count: int,
    heal_degraded_threads: bool = True,
    thread_catchup_pages: int = 8,
    force_open_chat: bool = False,
) -> tuple[Any, int]:
    """オープンチャット同期（メイン → discover → スレッド）。exit_code を返す。"""
    from chrline_client_utils import format_square_probe_report, probe_square_session_detail

    del allow_qr_login  # フェーズ入口では再QRしない（起動時の1回のみ）
    _run_chrline_version_check_if_needed()
    exit_code = 0
    # 第2 QR 禁止: refresh_square は常に無 QR
    cl = refresh_square_logged_in_client(save_root, allow_qr_login=False, cl=cl)
    if cl is None:
        print(
            "# open-chat skipped: session_dead_after_sync no_second_qr"
            " （別プロセスで --skip-sync --allow-qr-login を検討）",
            file=sys.stderr,
        )
        return cl, exit_code

    probe_detail = probe_square_session_detail(cl)
    if not probe_detail.get("ok") and not force_open_chat:
        print(format_square_probe_report(probe_detail), flush=True)
        print(
            "# open-chat スキップ: Square API 401（構造限界）。"
            " 強制実行: --force-open-chat / Phase0: chrline_square_probe_phase0.py",
            file=sys.stderr,
        )
        _record_square_probe_state(probe_detail)
        return cl, exit_code

    open_args_main = open_chat_mod.build_arg_parser().parse_args(["--no-threads"])
    rc = open_chat_mod.run(open_args_main, client=cl)
    if rc != 0:
        exit_code = rc

    # メイン後のセッション切断で discover / threads に進まないよう無 QR 再確認
    cl = _ensure_square_alive_no_qr(cl, save_root, phase="main")
    if cl is None:
        print("# thread sync: スキップのためなし（main後セッション切断）", file=sys.stderr)
        return cl, exit_code

    if discover_thread_mids_dry_run:
        discover_argv = ["--discover-thread-mids", "--dry-run", "--no-threads"]
        if discover_init:
            discover_argv.append("--init")
            discover_argv.append("--max-pages-per-stream=50")
        if discover_min_hit_count > 1:
            discover_argv.extend(["--min-hit-count", str(discover_min_hit_count)])
        discover_args = open_chat_mod.build_arg_parser().parse_args(discover_argv)
        drc = open_chat_mod.run(discover_args, client=cl)
        if drc != 0 and exit_code == 0:
            exit_code = drc

    cl = _ensure_square_alive_no_qr(cl, save_root, phase="discover")
    if cl is None:
        print("# thread sync: スキップのためなし（discover後セッション切断）", file=sys.stderr)
        return cl, exit_code

    thread_argv = ["--threads-only"]
    if heal_degraded_threads:
        thread_argv.append("--heal-degraded-threads")
    if thread_catchup_pages > 0:
        thread_argv.extend(["--thread-catchup-pages", str(thread_catchup_pages)])
    open_args_threads = open_chat_mod.build_arg_parser().parse_args(thread_argv)
    rc2 = open_chat_mod.run(open_args_threads, client=cl)
    if rc2 != 0 and exit_code == 0:
        exit_code = rc2
    return cl, exit_code


def _run_sync_phase(
    cl,
    *,
    save_root,
    allow_qr_login: bool,
    sync_preset: str,
    improved: bool,
    line_health: bool,
    line_health_since_days: int,
) -> tuple[Any, int]:
    exit_code = 0
    if cl is None:
        cl = refresh_logged_in_client(save_root, allow_qr_login=allow_qr_login, cl=cl)
    sync_argv = _build_sync_argv(sync_preset, improved=improved)
    sync_args = sync_mod.build_arg_parser().parse_args(sync_argv)
    rc = sync_mod.run(sync_args, client=cl)
    if rc != 0:
        exit_code = rc

    if line_health and rc == 0:
        try:
            _inv, health_block = run_line_health_routine(
                since_days=int(line_health_since_days),
                save_baseline=True,
                save_root=save_root,
            )
            print(health_block, flush=True)
        except Exception as e:
            print(f"# LINE本文ヘルス: スキップ（{type(e).__name__}: {e}）", file=sys.stderr)
    return cl, exit_code


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    if args.skip_sync and args.skip_open_chat:
        print("エラー: --skip-sync と --skip-open-chat を同時に指定できません。", file=sys.stderr)
        return 1

    save_root = save_root_from_env()
    # プロセスあたり QR は最大1回（既定 LINE_CHRLINE_MAX_QR_PER_PROCESS=1）。第2 QR は出さない。
    cl = build_logged_in_client(save_root, allow_qr_login=bool(args.allow_qr_login))

    heal_threads = not bool(args.no_heal_degraded_threads)
    catchup_pages = int(args.thread_catchup_pages)

    exit_code = 0
    open_chat_first = bool(args.open_chat_first)

    if open_chat_first:
        if not args.skip_open_chat:
            cl, oc_rc = _run_open_chat_phases(
                cl,
                save_root=save_root,
                allow_qr_login=bool(args.allow_qr_login),
                discover_thread_mids_dry_run=bool(args.discover_thread_mids_dry_run),
                discover_init=bool(args.discover_init),
                discover_min_hit_count=int(args.discover_min_hit_count),
                heal_degraded_threads=heal_threads,
                thread_catchup_pages=catchup_pages,
                force_open_chat=bool(args.force_open_chat),
            )
            if oc_rc != 0:
                exit_code = oc_rc
        if not args.skip_sync:
            cl, sync_rc = _run_sync_phase(
                cl,
                save_root=save_root,
                allow_qr_login=bool(args.allow_qr_login),
                sync_preset=args.sync_preset,
                improved=not args.skip_sync_improved_params,
                line_health=bool(args.line_health),
                line_health_since_days=int(args.line_health_since_days),
            )
            if sync_rc != 0 and exit_code == 0:
                exit_code = sync_rc
    else:
        if not args.skip_sync:
            cl, sync_rc = _run_sync_phase(
                cl,
                save_root=save_root,
                allow_qr_login=bool(args.allow_qr_login),
                sync_preset=args.sync_preset,
                improved=not args.skip_sync_improved_params,
                line_health=bool(args.line_health),
                line_health_since_days=int(args.line_health_since_days),
            )
            if sync_rc != 0:
                exit_code = sync_rc
        if not args.skip_open_chat:
            cl, oc_rc = _run_open_chat_phases(
                cl,
                save_root=save_root,
                allow_qr_login=bool(args.allow_qr_login),
                discover_thread_mids_dry_run=bool(args.discover_thread_mids_dry_run),
                discover_init=bool(args.discover_init),
                discover_min_hit_count=int(args.discover_min_hit_count),
                heal_degraded_threads=heal_threads,
                thread_catchup_pages=catchup_pages,
                force_open_chat=bool(args.force_open_chat),
            )
            if oc_rc != 0 and exit_code == 0:
                exit_code = oc_rc

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
