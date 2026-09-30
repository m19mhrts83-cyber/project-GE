#!/usr/bin/env python3
"""
Zaim 費目カタログの二重管理チェック。

正本: config/zaim_category_catalog.yaml
ミラー: apps/jarvis-dashboard/lib/zaimCategoryCatalog.ts
        （Vercel の Root Directory は apps/jarvis-dashboard のため、
          アプリはリポジトリ直下の config/ をビルド時に読めない。よって TS 側に持つ）

両者（value / label / group / genres）と順序が一致しなければ exit 1。
CI: .github/workflows/zaim-catalog-check.yml

  python scripts/jarvis_zaim_category_catalog_check.py
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
YAML_PATH = REPO / "config" / "zaim_category_catalog.yaml"
TS_PATH = REPO / "apps" / "jarvis-dashboard" / "lib" / "zaimCategoryCatalog.ts"

ENTRY_RE = re.compile(
    r'\{\s*value:\s*"([^"]*)"\s*,\s*label:\s*"([^"]*)"\s*,\s*group:\s*"([^"]*)"'
    r'\s*,\s*genres:\s*(\[[^\]]*\])\s*,?\s*\}',
    re.S,
)


def load_yaml_entries() -> list[tuple[str, str, str, tuple[str, ...]]]:
    import yaml

    data = yaml.safe_load(YAML_PATH.read_text(encoding="utf-8")) or {}
    out: list[tuple[str, str, str, tuple[str, ...]]] = []
    for c in data.get("categories") or []:
        out.append(
            (
                str(c.get("value", "")),
                str(c.get("label", "")),
                str(c.get("group", "")),
                tuple(str(g) for g in (c.get("genres") or [])),
            )
        )
    return out


def load_ts_entries() -> list[tuple[str, str, str, tuple[str, ...]]]:
    text = TS_PATH.read_text(encoding="utf-8")
    out: list[tuple[str, str, str, tuple[str, ...]]] = []
    for m in ENTRY_RE.finditer(text):
        value, label, group, genres_raw = m.groups()
        try:
            genres = json.loads(genres_raw)
        except json.JSONDecodeError:
            genres = []
        out.append((value, label, group, tuple(str(g) for g in genres)))
    return out


def main() -> int:
    try:
        y = load_yaml_entries()
    except FileNotFoundError:
        print(f"NG: not found: {YAML_PATH}", file=sys.stderr)
        return 1
    except Exception as e:  # yaml 未導入など
        print(f"NG: YAML 読込失敗: {e}", file=sys.stderr)
        return 1
    if not TS_PATH.is_file():
        print(f"NG: not found: {TS_PATH}", file=sys.stderr)
        return 1

    t = load_ts_entries()
    if y == t:
        print(f"ok: {len(y)} categories match (yaml == ts)")
        return 0

    print("NG: Zaim 費目カタログが YAML と TS でズレています", file=sys.stderr)
    ys, ts = set(y), set(t)
    for e in y:
        if e not in ts:
            print(f"  yaml のみ: {e}", file=sys.stderr)
    for e in t:
        if e not in ys:
            print(f"  ts のみ:   {e}", file=sys.stderr)
    if [e[0] for e in y] != [e[0] for e in t]:
        print("  順序も不一致（YAML 正本の順に合わせてください）", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
