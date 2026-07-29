#!/usr/bin/env python3
"""
未参加スレッドの join / fetch を個別に切り分ける（関西・全体周知など）。

使い方:
  cd ~/git-repos/line_unofficial_poc
  ./run_patch.sh chrline_join_thread_probe.py --allow-qr-login \\
    --route-ids 01_zentai_shuuchi_g 11_kansai_chiiki_g
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
    import yaml

    data = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
    return data.get("routes") or []


def _exc_detail(exc: BaseException) -> str:
    code = getattr(exc, "code", None)
    msg = str(exc).replace("\n", " ")[:240]
    return f"{type(exc).__name__}(code={code}): {msg}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Square thread join/fetch probe")
    parser.add_argument("--allow-qr-login", action="store_true")
    parser.add_argument("--route-ids", nargs="+", required=True)
    parser.add_argument("--routes-yaml", type=Path, default=None)
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--try-join", action="store_true", help="join API も試す（既定は fetch のみ）")
    args = parser.parse_args(argv)

    save_root = save_root_from_env()
    cl = build_logged_in_client(save_root, allow_qr_login=bool(args.allow_qr_login))
    if not probe_square_session(cl):
        print("エラー: Square probe NG", file=sys.stderr)
        return 1

    yaml_path = args.routes_yaml or (ROOT / "open_chat_routes.yaml")
    allowed = {x.strip() for x in args.route_ids if x.strip()}
    targets: list[tuple[str, str, str]] = []
    for row in _load_routes(yaml_path):
        rid = str(row.get("id") or "")
        if rid not in allowed:
            continue
        chat_mid = str(row.get("square_chat_mid") or "").strip()
        for tmid in row.get("thread_mids") or []:
            t = str(tmid).strip()
            if t and chat_mid:
                targets.append((rid, chat_mid, t))

    if not targets:
        print("エラー: 対象なし", file=sys.stderr)
        return 1

    print(f"# join/fetch probe targets={len(targets)} try_join={args.try_join}", file=sys.stderr)
    for rid, chat_mid, tmid in targets:
        print(f"\n# --- {rid} thread={tmid} ---", file=sys.stderr)

        # 1) getSquareThread (存在・権限)
        try:
            chrline_throttle()
            if hasattr(cl, "getSquareThread"):
                res = cl.getSquareThread(chat_mid, tmid)
                print(f"# getSquareThread OK type={type(res).__name__}", file=sys.stderr)
            else:
                print("# getSquareThread: method missing", file=sys.stderr)
        except Exception as e:
            print(f"# getSquareThread FAIL {_exc_detail(e)}", file=sys.stderr)

        # 2) fetch without join
        try:
            chrline_throttle()
            res = cl.fetchSquareChatEvents(
                chat_mid,
                syncToken=None,
                continuationToken=None,
                limit=max(1, min(args.limit, 50)),
                threadMid=tmid,
            )
            events = []
            if isinstance(res, dict):
                events = res.get("events") or res.get(1) or []
            elif hasattr(res, "events"):
                events = getattr(res, "events") or []
            n = len(events) if hasattr(events, "__len__") else "?"
            print(f"# fetch(no-join) OK events={n}", file=sys.stderr)
        except Exception as e:
            print(f"# fetch(no-join) FAIL {_exc_detail(e)}", file=sys.stderr)

        if not args.try_join:
            continue

        # 3) join variants
        for method in ("joinSquareThread", "joinSquareChatThread"):
            if not hasattr(cl, method):
                print(f"# {method}: method missing", file=sys.stderr)
                continue
            try:
                chrline_throttle()
                getattr(cl, method)(chat_mid, tmid)
                print(f"# {method} OK", file=sys.stderr)
            except Exception as e:
                print(f"# {method} FAIL {_exc_detail(e)}", file=sys.stderr)

        # 4) fetch after join attempt
        try:
            chrline_throttle()
            res = cl.fetchSquareChatEvents(
                chat_mid,
                syncToken=None,
                continuationToken=None,
                limit=max(1, min(args.limit, 50)),
                threadMid=tmid,
            )
            events = []
            if isinstance(res, dict):
                events = res.get("events") or res.get(1) or []
            elif hasattr(res, "events"):
                events = getattr(res, "events") or []
            n = len(events) if hasattr(events, "__len__") else "?"
            print(f"# fetch(after-join) OK events={n}", file=sys.stderr)
        except Exception as e:
            print(f"# fetch(after-join) FAIL {_exc_detail(e)}", file=sys.stderr)

    print("# probe done", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
