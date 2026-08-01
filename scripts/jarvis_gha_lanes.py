#!/usr/bin/env python3
"""
Jarvis GHA: コンテンツレーン要約 → cards upsert（Graph 未設定時はスキップ）

  # ローカル（OneDrive マウントあり）
  python scripts/jarvis_gha_lanes.py --push

  # GHA: MS_GRAPH_* が無いと exit 0 でスキップ（Mac 夜間 push が正）
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))

from jarvis_dashboard_lanes import collect, push_supabase  # noqa: E402
from jarvis_onedrive_graph import graph_configured  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--push", action="store_true")
    ap.add_argument("--force-local", action="store_true", help="Graph無しでもローカル収集を試す")
    args = ap.parse_args(argv)

    on_gha = bool(os.environ.get("GITHUB_ACTIONS"))
    if on_gha and not graph_configured() and not args.force_local:
        print(
            "# skip: MS_GRAPH_* 未設定。レーン要約のクラウド収集は Graph 配線後。"
            " Mac の jarvis_dashboard_lanes.py --push が当面の正本。",
            file=sys.stderr,
        )
        return 0

    result = collect()
    total = int((result.get("counts") or {}).get("total") or 0)
    print(f"# lanes collected total={total}", file=sys.stderr)
    if total == 0 and on_gha:
        print("# warn: 0 cards（パス未解決の可能性）", file=sys.stderr)
        return 0
    if args.push:
        n = push_supabase(result)
        print(f"# pushed {n}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
