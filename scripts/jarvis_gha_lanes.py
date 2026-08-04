#!/usr/bin/env python3
"""
Jarvis GHA: レーン要約確認（digest）→ cards upsert

機械的な大量カードは作らない（config/dashboard_lanes.yaml の max_auto_cards=0）。
正本フローは jarvis_lane_digest.py（Mac の dashboard push と同じ）。

  python scripts/jarvis_gha_lanes.py --push
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))

from jarvis_dashboard_lanes import YAML_PATH  # noqa: E402
from jarvis_lane_digest import main as digest_main  # noqa: E402
from jarvis_onedrive_graph import LOCAL_ONEDRIVE, graph_configured, read_file  # noqa: E402

CACHE = REPO / ".cache" / "onedrive_lanes"


def _rel_from_onedrive(path: Path) -> str | None:
    try:
        return str(path.expanduser().resolve().relative_to(LOCAL_ONEDRIVE.resolve()))
    except Exception:
        s = str(path)
        marker = "OneDrive-個人用/"
        if marker in s:
            return s.split(marker, 1)[1]
        if s.startswith("215_") or "/215_" in s:
            idx = s.find("215_")
            return s[idx:]
        return None


def materialize_via_graph() -> dict[str, str]:
    """YAML 上の OneDrive パスを Graph で取得し CACHE に展開。env override 用パスを返す。"""
    reg = yaml.safe_load(YAML_PATH.read_text(encoding="utf-8")) or {}
    partner = Path(reg.get("partner_base", "")).expanduser()
    kodate = Path(reg.get("kodate_actions", "")).expanduser()
    partner_rel = _rel_from_onedrive(partner)
    if not partner_rel:
        raise SystemExit("partner_base を OneDrive 相対パスにできません")
    cache_partner = CACHE / partner_rel
    overrides = {
        "JARVIS_LANES_PARTNER_BASE": str(cache_partner),
        "JARVIS_LANES_KODATE_ACTIONS": str(
            CACHE / (_rel_from_onedrive(kodate) or "kodate.md")
        ),
    }

    paths: list[Path] = []
    for lane in reg.get("lanes") or []:
        for src in lane.get("sources") or []:
            raw = str(src.get("path") or "")
            p = Path(
                raw.replace("{partner_base}", str(partner))
                .replace("{kodate_actions}", str(kodate))
                .replace(
                    "{obsidian_journal}",
                    str(Path(reg.get("obsidian_journal", "")).expanduser()),
                )
            ).expanduser()
            if src.get("kind") == "journal_recent":
                print(f"# skip journal_recent on GHA for now: {p}", file=sys.stderr)
                continue
            paths.append(p)

    for p in paths:
        rel = _rel_from_onedrive(p)
        if not rel:
            print(f"# skip non-onedrive path: {p}", file=sys.stderr)
            continue
        dest = CACHE / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        data = read_file("onedrive", rel)
        dest.write_bytes(data)
        print(f"# cached {rel} ({len(data)} bytes)", file=sys.stderr)
    return overrides


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--push", action="store_true")
    ap.add_argument(
        "--force-local",
        action="store_true",
        help="Graph無しでもローカル収集を試す",
    )
    ap.add_argument("--lane", default="", help="digest を1レーンに限定")
    args = ap.parse_args(argv)

    on_gha = bool(os.environ.get("GITHUB_ACTIONS"))
    if graph_configured():
        try:
            for k, v in materialize_via_graph().items():
                os.environ[k] = v
        except Exception as e:
            print(f"# graph materialize failed: {e}", file=sys.stderr)
            if on_gha and not args.force_local:
                return 1
    elif on_gha and not args.force_local:
        print(
            "# skip: MS_GRAPH_* 未設定（個人用は REFRESH_TOKEN）。"
            " 手順: docs/Jarvis_OneDrive_Graph.md / Mac の jarvis_lane_digest.py --push が正本。",
            file=sys.stderr,
        )
        return 0

    digest_argv = ["--no-log"]  # GHA は OneDrive MD に書けない
    if args.push:
        digest_argv.append("--push")
    if args.lane.strip():
        digest_argv.extend(["--lane", args.lane.strip()])
    print("# digest via jarvis_lane_digest (max_auto_cards=0)", file=sys.stderr)
    return digest_main(digest_argv)


if __name__ == "__main__":
    raise SystemExit(main())
