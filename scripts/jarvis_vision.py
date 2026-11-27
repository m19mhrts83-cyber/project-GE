#!/usr/bin/env python3
"""ビジョンの文面を sync_meta `vision` に置く。/policy の一番上が読む（ログイン必須）。

文面は個人的な内容なので、このリポにも引数にも埋め込まない。Markdown ファイルから流し込む。
  python3 scripts/jarvis_vision.py --file <vision.md>   # そのまま保存（言い換えしない）
  python3 scripts/jarvis_vision.py --show
  python3 scripts/jarvis_vision.py --clear               # 欄ごと消す
形式: 「V1. …」の行と「  - …」の行（apps/jarvis-dashboard/lib/vision.ts）。
"""
from __future__ import annotations

import argparse
import os
import sys

KEY = "vision"


def client():
    url = (os.environ.get("JARVIS_SUPABASE_URL") or "").strip()
    key = (os.environ.get("JARVIS_SUPABASE_SERVICE_ROLE_KEY") or "").strip()
    if not url or not key:
        raise SystemExit("JARVIS_SUPABASE_* 未設定")
    from supabase import create_client
    return create_client(url, key)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--file")
    ap.add_argument("--show", action="store_true")
    ap.add_argument("--clear", action="store_true")
    a = ap.parse_args()
    c = client()
    if a.clear:
        c.table("sync_meta").delete().eq("key", KEY).execute()
        print("# cleared", file=sys.stderr)
        return 0
    if a.file:
        with open(a.file, encoding="utf-8") as f:
            text = f.read()
        if not text.strip():
            raise SystemExit("ファイルが空")
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        c.table("sync_meta").upsert({"key": KEY, "value": text, "updated_at": now}, on_conflict="key").execute()
        print(f"# saved ({len(text)} chars)", file=sys.stderr)
        return 0
    r = c.table("sync_meta").select("value").eq("key", KEY).maybe_single().execute()
    print(r.data["value"] if r and r.data else "(なし)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
