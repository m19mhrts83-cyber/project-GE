#!/usr/bin/env python3
"""line_openchat_logs: staging → ready / excluded（ノイズのみ除外・漏れなく公開）

方針:
  - 既定はほぼ全件 ready（検索公開）
  - NOISE_MARKERS（物件チラシ定型等）または空／非テキストのみ → excluded
  - 物件紹介ルート丸ごと除外はしない

使用例:
  cd ~/git-repos && set -a && source .env.jarvis_private && set +a
  python scripts/jarvis_openchat_publish.py --dry-run
  python scripts/jarvis_openchat_publish.py --apply
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))

from jarvis_kurashift_openchat_sync import (  # noqa: E402
    NOISE_MARKERS,
    load_dotenv_file,
    qa_sb,
    QA_ENV_CANDIDATES,
)

NON_TEXT_MARKERS = (
    "[非テキスト",
    "[本文なし]",
    "[E2EE",
)


def is_noise(content: str) -> bool:
    c = (content or "").strip()
    if not c:
        return True
    if any(m in c for m in NON_TEXT_MARKERS):
        return True
    if any(m in c for m in NOISE_MARKERS):
        return True
    return False


def fetch_all_staging_and_ready(sb: Any) -> list[dict[str, Any]]:
    """staging / ready / excluded を再評価対象に含める（再 publish 可）。"""
    rows: list[dict[str, Any]] = []
    page = 1000
    offset = 0
    while True:
        res = (
            sb.table("line_openchat_logs")
            .select("id,content,ingest_status")
            .in_("ingest_status", ["staging", "ready", "excluded", "active"])
            .range(offset, offset + page - 1)
            .execute()
        )
        chunk = list(res.data or [])
        rows.extend(chunk)
        if len(chunk) < page:
            break
        offset += page
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description="Publish LINE openchat logs to ready/excluded")
    parser.add_argument("--dry-run", action="store_true", help="件数だけ表示（既定）")
    parser.add_argument("--apply", action="store_true", help="DB を更新")
    args = parser.parse_args()
    do_apply = bool(args.apply)
    if not do_apply and not args.dry_run:
        args.dry_run = True

    for p in QA_ENV_CANDIDATES:
        load_dotenv_file(p)
    sb = qa_sb()

    rows = fetch_all_staging_and_ready(sb)
    ready_ids: list[str] = []
    excluded_ids: list[str] = []
    for r in rows:
        rid = str(r.get("id") or "")
        if not rid:
            continue
        if is_noise(str(r.get("content") or "")):
            excluded_ids.append(rid)
        else:
            ready_ids.append(rid)

    print(
        f"📎 openchat publish — 対象 {len(rows)} 件"
        f" / ready候補 {len(ready_ids)} / excluded候補 {len(excluded_ids)}"
        f" / mode={'APPLY' if do_apply else 'DRY-RUN'}"
    )
    if not do_apply:
        print("ℹ️ 反映するには --apply")
        return 0

    now = datetime.now(timezone.utc).isoformat()
    upserted = 0
    batch = 80

    def bump(ids: list[str], status: str) -> int:
        n = 0
        for i in range(0, len(ids), batch):
            chunk = ids[i : i + batch]
            # upsert だと必須列が null になり失敗するため update のみ
            res = (
                sb.table("line_openchat_logs")
                .update({"ingest_status": status, "updated_at": now})
                .in_("id", chunk)
                .execute()
            )
            n += len(res.data or [])
        return n

    upserted += bump(ready_ids, "ready")
    upserted += bump(excluded_ids, "excluded")
    print(f"✅ UPSERT 応答行数: {upserted}（ready={len(ready_ids)} excluded={len(excluded_ids)}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
