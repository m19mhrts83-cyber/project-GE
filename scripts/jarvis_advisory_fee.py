#!/usr/bin/env python3
"""AI 顧問料（固定＋月ごとの追加費用）を sync_meta `advisory_fee` に置く。/policy の「見合い」が読む。

Zaim からは拾えない収入なので別に持つ。公開リポなので金額はここに書かず、コマンドの引数で渡す。
  python3 scripts/jarvis_advisory_fee.py --show
  python3 scripts/jarvis_advisory_fee.py --fixed <円> --from 2026-11     # 固定分と、その開始月
  python3 scripts/jarvis_advisory_fee.py --extra 2026-11=<円>            # 改修対応などの追加費用（月ごと・上書き）
追加費用は /policy の入力欄からも入れられる（同じ値を読み書きする）。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

KEY = "advisory_fee"


def client():
    url = (os.environ.get("JARVIS_SUPABASE_URL") or "").strip()
    key = (os.environ.get("JARVIS_SUPABASE_SERVICE_ROLE_KEY") or "").strip()
    if not url or not key:
        raise SystemExit("JARVIS_SUPABASE_* 未設定")
    from supabase import create_client
    return create_client(url, key)


def load(c) -> dict:
    r = c.table("sync_meta").select("value").eq("key", KEY).maybe_single().execute()
    try:
        v = json.loads(r.data["value"]) if r and r.data else {}
    except Exception:
        v = {}
    v.setdefault("fixed_yen", 0)
    v.setdefault("fixed_from", None)
    v.setdefault("extras", {})
    return v


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--show", action="store_true")
    ap.add_argument("--fixed", type=int)
    ap.add_argument("--from", dest="from_ym")
    ap.add_argument("--extra", action="append", default=[], metavar="YYYY-MM=円")
    a = ap.parse_args()
    c = client()
    v = load(c)
    changed = False
    if a.fixed is not None:
        if a.fixed < 0:
            raise SystemExit("--fixed は0以上")
        v["fixed_yen"] = a.fixed
        changed = True
    if a.from_ym:
        if not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", a.from_ym):
            raise SystemExit("--from は YYYY-MM")
        v["fixed_from"] = a.from_ym
        changed = True
    for e in a.extra:
        m = re.fullmatch(r"(\d{4}-(?:0[1-9]|1[0-2]))=(\d+)", e)
        if not m:
            raise SystemExit(f"--extra は YYYY-MM=円: {e}")
        v["extras"][m.group(1)] = int(m.group(2))
        changed = True
    if changed:
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        c.table("sync_meta").upsert(
            {"key": KEY, "value": json.dumps(v, ensure_ascii=False), "updated_at": now}, on_conflict="key"
        ).execute()
        print("# saved", file=sys.stderr)
    if a.show or not changed:
        print(json.dumps(v, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
