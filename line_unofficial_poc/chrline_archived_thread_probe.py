#!/usr/bin/env python3
"""thread_mids_archived を1件ずつ probe する（30空室 archived 57 再検証用）。"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

from chrline_client_utils import (
    build_logged_in_client,
    chrline_throttle,
    probe_square_session,
    save_root_from_env,
)

ROOT = Path(__file__).resolve().parent


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="archived thread_mids probe")
    parser.add_argument("--allow-qr-login", action="store_true")
    parser.add_argument("--route-ids", nargs="+", required=True)
    parser.add_argument("--ok-out", type=Path, default=None)
    parser.add_argument("--ng-out", type=Path, default=None)
    args = parser.parse_args(argv)

    yaml_path = ROOT / "open_chat_routes.yaml"
    routes = yaml.safe_load(yaml_path.read_text(encoding="utf-8")).get("routes") or []
    allowed = {x.strip() for x in args.route_ids if x.strip()}

    targets: list[tuple[str, str, str]] = []
    for row in routes:
        rid = str(row.get("id") or "")
        if rid not in allowed:
            continue
        chat = str(row.get("square_chat_mid") or "").strip()
        label = str(row.get("org_label") or rid)
        for tmid in row.get("thread_mids_archived") or []:
            t = str(tmid).strip()
            if t and chat:
                targets.append((chat, t, label))

    if not targets:
        print("エラー: archived 対象がありません", file=sys.stderr)
        return 1

    cl = build_logged_in_client(save_root_from_env(), allow_qr_login=bool(args.allow_qr_login))
    if not probe_square_session(cl):
        print("エラー: Square probe NG", file=sys.stderr)
        return 1

    ok_list: list[str] = []
    ng_list: list[str] = []
    print(f"# archived probe: {len(targets)} 件", file=sys.stderr)
    for chat_mid, thread_mid, label in targets:
        try:
            chrline_throttle()
            cl.fetchSquareChatEvents(chat_mid, limit=1, threadMid=thread_mid)
            ok_list.append(thread_mid)
            print(f"OK  {label} {thread_mid[:12]}…", file=sys.stderr)
        except Exception as exc:
            ng_list.append(thread_mid)
            print(f"NG  {label} {thread_mid[:12]}… {type(exc).__name__}: {exc}", file=sys.stderr)

    print(
        f"# archived probe 結果: ok={len(ok_list)} ng={len(ng_list)} total={len(targets)}",
        file=sys.stderr,
    )
    if args.ok_out:
        args.ok_out.write_text("\n".join(ok_list) + ("\n" if ok_list else ""), encoding="utf-8")
    if args.ng_out:
        args.ng_out.write_text("\n".join(ng_list) + ("\n" if ng_list else ""), encoding="utf-8")
    return 0 if ok_list else 1


if __name__ == "__main__":
    raise SystemExit(main())
