#!/usr/bin/env python3
"""Jarvis Dashboard の資料ハブ定義を、外部アクセスなしで点検する。"""
from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import urlparse

REPO = Path(__file__).resolve().parents[1]
CATALOG = REPO / "apps" / "jarvis-dashboard" / "data" / "materials_catalog.json"


def audit(data: dict) -> list[str]:
    errors: list[str] = []
    lanes = data.get("lanes") if isinstance(data.get("lanes"), list) else []
    items = data.get("items") if isinstance(data.get("items"), list) else []
    lane_ids = [str(row.get("id") or "") for row in lanes if isinstance(row, dict)]
    item_ids = [str(row.get("id") or "") for row in items if isinstance(row, dict)]
    if len(lane_ids) != len(set(lane_ids)):
        errors.append("lane id が重複")
    if len(item_ids) != len(set(item_ids)):
        errors.append("item id が重複")
    for row_type, rows in (("lane", lanes), ("item", items)):
        for row in rows:
            if not isinstance(row, dict):
                errors.append(f"{row_type}: オブジェクトではない")
                continue
            row_id = str(row.get("id") or "(idなし)")
            url = str(row.get("hub_url") if row_type == "lane" else row.get("url") or "")
            parsed = urlparse(url)
            if parsed.scheme not in {"https", "http"} or not parsed.netloc:
                errors.append(f"{row_type}:{row_id}: URL不正")
            if row_type == "lane" and parsed.path.lower().endswith(".md"):
                errors.append(f"lane:{row_id}: ブラウザ用ハブがMarkdown直リンク")
            if row_type == "item" and row.get("lane") not in lane_ids:
                errors.append(f"item:{row_id}: lane未定義 {row.get('lane')}")
    return errors


def main() -> int:
    data = json.loads(CATALOG.read_text(encoding="utf-8"))
    errors = audit(data)
    summary = {
        "catalog": str(CATALOG.relative_to(REPO)),
        "lanes": len(data.get("lanes") or []),
        "items": len(data.get("items") or []),
        "status": "ok" if not errors else "error",
        "errors": errors,
        "note": "URL定義の構文・重複・所属を確認。リンク先の権限や内容はブラウザで別確認。",
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
