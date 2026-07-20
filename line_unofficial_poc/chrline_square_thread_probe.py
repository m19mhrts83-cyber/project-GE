#!/usr/bin/env python3
"""
815 オープンチャットのスレッドを1件ずつ fetchSquareChatEvents して 401/OK を切り分ける。

バッチ401調査用。run_patch.sh 経由で実行する。

使い方:
  cd ~/git-repos/line_unofficial_poc
  ./run_patch.sh chrline_square_thread_probe.py --route-ids 30_kuushitsu_soudan_g
  ./run_patch.sh chrline_square_thread_probe.py --thread-mid t03c8f5bc4f5c1738d3fb5625db1ae6ee --square-chat-mid m82a451eb96a535983d9cd8d172820c19
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from chrline_client_utils import (
    build_logged_in_client,
    chrline_throttle,
    probe_square_session,
    save_root_from_env,
)

ROOT = Path(__file__).resolve().parent


def _load_routes(yaml_path: Path):
    try:
        import yaml
    except ImportError:
        print("エラー: PyYAML が必要です", file=sys.stderr)
        raise SystemExit(1)
    data = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
    return data.get("routes") or []


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Square スレッド単位 probe")
    parser.add_argument("--allow-qr-login", action="store_true")
    parser.add_argument("--route-ids", nargs="+", default=[])
    parser.add_argument("--thread-mid", default="")
    parser.add_argument("--square-chat-mid", default="")
    parser.add_argument(
        "--routes-yaml",
        type=Path,
        default=None,
        help="未指定時 open_chat_routes.yaml",
    )
    args = parser.parse_args(argv)

    save_root = save_root_from_env()
    cl = build_logged_in_client(save_root, allow_qr_login=bool(args.allow_qr_login))
    if not probe_square_session(cl):
        print("エラー: Square probe NG（メイン+代表スレッド）", file=sys.stderr)
        return 1

    targets: list[tuple[str, str, str]] = []
    if args.thread_mid and args.square_chat_mid:
        targets.append((args.square_chat_mid, args.thread_mid, "manual"))
    else:
        yaml_path = args.routes_yaml or (ROOT / "open_chat_routes.yaml")
        allowed = {x.strip() for x in args.route_ids if x.strip()}
        for row in _load_routes(yaml_path):
            rid = str(row.get("id") or "")
            if allowed and rid not in allowed:
                continue
            chat_mid = str(row.get("square_chat_mid") or "").strip()
            org = str(row.get("org_label") or rid)
            for tmid in row.get("thread_mids") or []:
                t = str(tmid).strip()
                if t and chat_mid:
                    targets.append((chat_mid, t, org))

    if not targets:
        print("エラー: 対象スレッドがありません", file=sys.stderr)
        return 1

    ok_n = 0
    fail_n = 0
    print(f"# thread probe: {len(targets)} 件", file=sys.stderr)
    for chat_mid, thread_mid, label in targets:
        try:
            chrline_throttle()
            cl.fetchSquareChatEvents(chat_mid, limit=1, threadMid=thread_mid)
            ok_n += 1
            print(f"OK  {label} {thread_mid[:12]}…", file=sys.stderr)
        except Exception as exc:
            fail_n += 1
            print(
                f"NG  {label} {thread_mid[:12]}… {type(exc).__name__}: {exc}",
                file=sys.stderr,
            )

    print(
        f"# thread probe 結果: ok={ok_n} ng={fail_n} total={len(targets)}",
        file=sys.stderr,
    )
    return 0 if ok_n > 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
