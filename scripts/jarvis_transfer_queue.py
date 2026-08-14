#!/usr/bin/env python3
"""送金アシスト横断キュー（Wave4 骨格）。

承認済み money-ops のレール順を表示し、次に叩く Terminal コマンドを出す。
記帳はしない（各ランチャの Preview→Go に委譲）。

  python scripts/jarvis_transfer_queue.py
  python scripts/jarvis_transfer_queue.py --money-ops-id UUID
"""

from __future__ import annotations

import argparse
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[1]
RAILS_YAML = REPO / "config" / "kurashift_transfer_rails.yaml"
LAUNCH_DIR = REPO / "215_kamiooya" / "C1_cursor" / "browser_automation"


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--money-ops-id", default="")
    args = p.parse_args()
    data = yaml.safe_load(RAILS_YAML.read_text(encoding="utf-8")) or {}
    rails = sorted(data.get("rails") or [], key=lambda r: int(r.get("order") or 99))
    blocked = data.get("blocked") or []
    mid = f" --money-ops-id {args.money_ops_id}" if args.money_ops_id else ""
    print("=== 送金アシスト キュー（Wave4）===")
    print("順序: 無料(SBI) → ≤10万かつAW可ならエアウォレット → IB他行。並列禁止・間隔≥60秒")
    if args.money_ops_id:
        print(f"money_ops_id: {args.money_ops_id}")
    print(f"cwd: {LAUNCH_DIR}")
    print("")
    for r in rails:
        if not r.get("enabled", True):
            continue
        amt = r.get("amount_jpy")
        amt_s = f"{int(amt):,}円" if amt is not None else "—"
        print(f"- [{r.get('order')}] {r.get('label')}  {amt_s}")
        print(f"    otp={r.get('otp_channel')}  runner={r.get('runner')}")
        launcher = r.get("launcher") or ""
        if launcher.endswith(".sh"):
            base = Path(launcher).name
            print(f"    ./{base} --preview")
            print(f"    ./{base} --go{mid}")
        print("")
    if blocked:
        print("blocked:")
        for b in blocked:
            print(f"  - {b.get('id')}: {b.get('reason')}")
    print("※ 実行は Terminal.app。承認だけでは動きません。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
