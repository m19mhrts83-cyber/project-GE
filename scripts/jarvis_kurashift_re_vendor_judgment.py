#!/usr/bin/env python3
"""地場業者返信の判断 → YAML notes 追記 → Supabase 投影。

Dashboard の applyVendorReplyJudgment が enqueue する re_vendor_judgment を処理する。

  python scripts/jarvis_kurashift_re_vendor_judgment.py \\
    --vendor-id chubu-016 --note "2026-08-30 返信判断: 担当待ち"
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PY = Path("/Users/matsunomasaharu2/selenium_env/venv/bin/python")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--vendor-id", required=True)
    ap.add_argument("--note", required=True)
    ap.add_argument("--judgment", default="", help="await_staff|no_reply|later（ログ用）")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    sys.path.insert(0, str(REPO / "scripts"))
    from jarvis_kurashift_vendor_list import append_vendor_note  # noqa: E402

    out = append_vendor_note(args.vendor_id, args.note, dry_run=args.dry_run)
    print(json.dumps(out, ensure_ascii=False, indent=2))
    if not out.get("ok"):
        return 1

    if args.dry_run:
        print("KURASHIFT_RESULT:" + json.dumps({"append_note": out, "sync": "dry_run"}, ensure_ascii=False))
        return 0

    py = str(PY if PY.exists() else sys.executable)
    sync = subprocess.run(
        [py, str(REPO / "scripts" / "jarvis_kurashift_vendor_sync.py"), "--apply"],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        timeout=120,
    )
    log_tail = ((sync.stdout or "") + (sync.stderr or ""))[-4000:]
    if sync.returncode != 0:
        print(log_tail, file=sys.stderr)
        return sync.returncode

    result = {
        "vendor_id": args.vendor_id,
        "judgment": args.judgment or None,
        "append_note": {"ok": True},
        "sync_returncode": sync.returncode,
    }
    print("KURASHIFT_RESULT:" + json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
