#!/usr/bin/env python3
"""YAML 正本と financePackCatalog.ts の slot id 差分（CATALOG-DRIFT 検知）。"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
YAML = ROOT / "config" / "kurashift_re_finance_doc_templates.yaml"
TS = ROOT / "apps" / "trade-desk" / "lib" / "financePackCatalog.ts"


def yaml_ids(text: str) -> set[str]:
    return set(re.findall(r"(?m)^\s*-\s*id:\s*([a-z0-9_]+)\s*$", text))


def ts_slot_ids(text: str) -> set[str]:
    """BANK_PROFILES より前の id のみ（書類スロット）。"""
    cut = text.find("export const BANK_PROFILES")
    body = text if cut < 0 else text[:cut]
    return set(re.findall(r'(?m)^\s*id:\s*"([a-z0-9_]+)"\s*,?\s*$', body))


def main() -> int:
    y = yaml_ids(YAML.read_text(encoding="utf-8"))
    t = ts_slot_ids(TS.read_text(encoding="utf-8"))
    only_y = sorted(y - t)
    only_t = sorted(t - y)
    print(f"yaml_slots={len(y)} ts_slots={len(t)}")
    if only_y:
        print("only_in_yaml:", ", ".join(only_y))
    if only_t:
        print("only_in_ts:", ", ".join(only_t))
    if only_y or only_t:
        print("STATUS=DRIFT")
        return 1
    print("STATUS=OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
