#!/usr/bin/env python3
"""line_openchat_logs: staging → ready / excluded（ノイズのみ除外・漏れなく公開）

方針:
  - 既定は **staging のみ** を評価（差分 sync と対）
  - NOISE_MARKERS（物件チラシ定型等）または空／非テキストのみ → excluded
  - 物件紹介ルート丸ごと除外はしない
  - 更新は return=minimal（embedding をレスポンスに載せない）
  - ノイズ規則の全面再適用は --reclassify-all

使用例:
  cd ~/git-repos && set -a && source .env.jarvis_private && set +a
  python scripts/jarvis_openchat_publish.py --dry-run
  python scripts/jarvis_openchat_publish.py --apply
  python scripts/jarvis_openchat_publish.py --apply --reclassify-all
"""

from __future__ import annotations

import argparse
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


def fetch_publish_targets(
    sb: Any,
    *,
    reclassify_all: bool,
) -> list[dict[str, Any]]:
    """既定は staging のみ。--reclassify-all で全ステータス再評価。"""
    statuses = (
        ["staging", "ready", "excluded", "active"]
        if reclassify_all
        else ["staging"]
    )
    rows: list[dict[str, Any]] = []
    page = 1000
    offset = 0
    while True:
        res = (
            sb.table("line_openchat_logs")
            .select("id,content,ingest_status")
            .in_("ingest_status", statuses)
            .range(offset, offset + page - 1)
            .execute()
        )
        chunk = list(res.data or [])
        rows.extend(chunk)
        if len(chunk) < page:
            break
        offset += page
    return rows


def _update_status_minimal(sb: Any, ids: list[str], status: str, now: str) -> int:
    if not ids:
        return 0
    n = 0
    batch = 80
    for i in range(0, len(ids), batch):
        chunk = ids[i : i + batch]
        try:
            from postgrest.types import ReturnMethod  # type: ignore

            sb.table("line_openchat_logs").update(
                {"ingest_status": status, "updated_at": now},
                returning=ReturnMethod.minimal,
            ).in_("id", chunk).execute()
            n += len(chunk)
        except TypeError:
            res = (
                sb.table("line_openchat_logs")
                .update({"ingest_status": status, "updated_at": now})
                .in_("id", chunk)
                .execute()
            )
            n += len(res.data or chunk)
        except Exception:
            res = (
                sb.table("line_openchat_logs")
                .update({"ingest_status": status, "updated_at": now})
                .in_("id", chunk)
                .execute()
            )
            n += len(res.data or chunk)
    return n


def main() -> int:
    parser = argparse.ArgumentParser(description="Publish LINE openchat logs to ready/excluded")
    parser.add_argument("--dry-run", action="store_true", help="件数だけ表示（既定）")
    parser.add_argument("--apply", action="store_true", help="DB を更新")
    parser.add_argument(
        "--reclassify-all",
        action="store_true",
        help="ready/excluded も含め全件を再分類（ノイズ規則変更時）",
    )
    args = parser.parse_args()
    do_apply = bool(args.apply)
    if not do_apply and not args.dry_run:
        args.dry_run = True

    for p in QA_ENV_CANDIDATES:
        load_dotenv_file(p)
    sb = qa_sb()

    rows = fetch_publish_targets(sb, reclassify_all=bool(args.reclassify_all))
    ready_ids: list[str] = []
    excluded_ids: list[str] = []
    skipped_same = 0
    for r in rows:
        rid = str(r.get("id") or "")
        if not rid:
            continue
        want = "excluded" if is_noise(str(r.get("content") or "")) else "ready"
        cur = str(r.get("ingest_status") or "")
        if cur == want:
            skipped_same += 1
            continue
        if want == "excluded":
            excluded_ids.append(rid)
        else:
            ready_ids.append(rid)

    scope = "reclassify-all" if args.reclassify_all else "staging-only"
    print(
        f"📎 openchat publish — scope={scope} 読取 {len(rows)} 件"
        f" / readyへ {len(ready_ids)} / excludedへ {len(excluded_ids)}"
        f" / 同一スキップ {skipped_same}"
        f" / mode={'APPLY' if do_apply else 'DRY-RUN'}"
    )
    if not do_apply:
        print("ℹ️ 反映するには --apply")
        return 0

    now = datetime.now(timezone.utc).isoformat()
    upserted = 0
    upserted += _update_status_minimal(sb, ready_ids, "ready", now)
    upserted += _update_status_minimal(sb, excluded_ids, "excluded", now)
    print(
        f"✅ 更新行数: {upserted}（ready={len(ready_ids)} excluded={len(excluded_ids)}）"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
