#!/usr/bin/env python3
"""KURASHIFT 不動産 — 日次ダイジェスト（要返信・業者フォロー）。

  cd ~/git-repos && set -a && source .env.jarvis_private && set +a
  ~/selenium_env/venv/bin/python scripts/jarvis_kurashift_re_daily_digest.py
  ~/selenium_env/venv/bin/python scripts/jarvis_kurashift_re_daily_digest.py --mark-reported

パートナー確認末尾・朝バンドル後に貼る。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
STATE_PATH = REPO / ".jarvis_state" / "kurashift_re_daily_digest.json"
FORM_URL = "https://form.os7.biz/f/1906a1a5/"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def sb_client() -> Any:
    url = os.environ.get("JARVIS_SUPABASE_URL")
    key = os.environ.get("JARVIS_SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        raise SystemExit("JARVIS_SUPABASE_URL / JARVIS_SUPABASE_SERVICE_ROLE_KEY が必要です")
    from supabase import create_client

    return create_client(url, key)


def load_state() -> dict[str, Any]:
    if not STATE_PATH.is_file():
        return {"reported_deals": {}, "last_run_at": None}
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"reported_deals": {}, "last_run_at": None}


def save_state(state: dict[str, Any]) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    state["last_run_at"] = now_iso()
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def run(*, mark_reported: bool) -> dict[str, Any]:
    sb = sb_client()
    state = load_state()
    reported: dict[str, str] = dict(state.get("reported_deals") or {})

    deals_r = (
        sb.table("kurashift_re_deals")
        .select("id, title, area, inquiry_status, status, updated_at")
        .eq("inquiry_status", "has_reply")
        .in_("status", ["info", "viewing"])
        .order("updated_at", desc=True)
        .limit(20)
        .execute()
    )
    has_reply = deals_r.data or []

    vendors_r = (
        sb.table("kurashift_re_vendors")
        .select("id", count="exact")
        .eq("status", "replied")
        .execute()
    )
    vendor_replied = int(getattr(vendors_r, "count", None) or 0)

    new_deals: list[dict[str, Any]] = []
    for d in has_reply:
        did = str(d.get("id") or "")
        if not did:
            continue
        if did not in reported or mark_reported:
            new_deals.append(d)

    lines = ["---", "📎 KURASHIFT不動産（日次）"]
    if not has_reply and vendor_replied == 0:
        lines.append("- 問合せ返信: 0件 · 業者返信フォロー: 0件")
        lines.append("- 判定: ✅ 要対応なし")
        lines.append("---")
        print("\n".join(lines))
        out = {"ok": True, "has_reply": 0, "vendor_replied": 0, "new": 0}
        if mark_reported:
            save_state(state)
        print("KURASHIFT_RESULT:" + json.dumps(out, ensure_ascii=False))
        return out

    lines.append(f"- 問合せ返信（has_reply）: {len(has_reply)}件")
    for d in has_reply[:5]:
        title = str(d.get("title") or d.get("area") or d.get("id", ""))[:50]
        lines.append(f"  · {title}")
    if len(has_reply) > 5:
        lines.append(f"  …他 {len(has_reply) - 5} 件")

    lines.append(f"- 業者返信フォロー（replied）: {vendor_replied}件")
    lines.append("- 次の一手:")
    lines.append("  1. /realestate/deals?tab=candidates&inquiry=has_reply")
    lines.append("  2. ドロワーで返信・PDF確認 → フォーム項目調査")
    lines.append("  3. 神大家個人Driveに資料格納")
    lines.append(f"  4. 運営相談フォーム（確認後送信）→ {FORM_URL}")
    lines.append("---")

    print("\n".join(lines))

    if mark_reported:
        for d in has_reply:
            did = str(d.get("id") or "")
            if did:
                reported[did] = now_iso()
        state["reported_deals"] = reported
        save_state(state)

    out = {
        "ok": True,
        "has_reply": len(has_reply),
        "vendor_replied": vendor_replied,
        "new": len(new_deals),
        "mark_reported": mark_reported,
    }
    print("KURASHIFT_RESULT:" + json.dumps(out, ensure_ascii=False))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--mark-reported",
        action="store_true",
        help="表示した deal を reported に記録",
    )
    args = ap.parse_args()
    run(mark_reported=args.mark_reported)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
