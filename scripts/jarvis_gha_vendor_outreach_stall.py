#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""GHA: 516 業者開拓フォロー（見守り）— YAML materialize → stall_runner --skip-refill.

Drive outbox 補給はしない（Mac 保険）。検知・sync_meta・Slack のみ。

  python scripts/jarvis_gha_vendor_outreach_stall.py --dry-run
  python scripts/jarvis_gha_vendor_outreach_stall.py --evening
  python scripts/jarvis_gha_vendor_outreach_stall.py --lane all

Secrets（gzip 後 B64・GitHub 64KB 上限対策）:
  KURASHIFT_RE_VENDOR_LIST_B64
  KURASHIFT_REPAIR_VENDOR_LIST_B64
  KURASHIFT_MGMT_VENDOR_LIST_B64

  設定例: gzip -9 -c config/kurashift_re_vendor_list.yaml | base64 | gh secret set …

停止: JARVIS_VENDOR_OUTREACH_STALL_GHA_DISABLE=1
"""
from __future__ import annotations

import argparse
import base64
import gzip
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

YAML_SECRETS = (
    ("KURASHIFT_RE_VENDOR_LIST_B64", "kurashift_re_vendor_list.yaml"),
    ("KURASHIFT_REPAIR_VENDOR_LIST_B64", "kurashift_repair_vendor_list.yaml"),
    ("KURASHIFT_MGMT_VENDOR_LIST_B64", "kurashift_mgmt_vendor_list.yaml"),
)


def _disabled() -> bool:
    return (os.environ.get("JARVIS_VENDOR_OUTREACH_STALL_GHA_DISABLE") or "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def _decode_secret_payload(data: bytes) -> bytes:
    """gzip magic なら展開。平文 YAML も可（ローカル検証用）。"""
    if len(data) >= 2 and data[0] == 0x1F and data[1] == 0x8B:
        return gzip.decompress(data)
    return data


def _b64_write(env_key: str, dest: Path) -> bool:
    raw = (os.environ.get(env_key) or "").strip()
    if not raw:
        return False
    try:
        packed = base64.b64decode(raw, validate=False)
        data = _decode_secret_payload(packed)
    except Exception as e:
        raise SystemExit(f"{env_key}: decode failed: {e}") from e
    if not data.strip():
        raise SystemExit(f"{env_key}: empty after decode")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
    print(f"# materialize {dest.name} ({len(data)} bytes)", file=sys.stderr)
    return True


def materialize_yamls() -> list[str]:
    cfg = REPO / "config"
    written: list[str] = []
    missing: list[str] = []
    for env_key, name in YAML_SECRETS:
        dest = cfg / name
        if _b64_write(env_key, dest):
            written.append(name)
        elif dest.is_file():
            print(f"# keep existing {name} (secret empty)", file=sys.stderr)
            written.append(name)
        else:
            missing.append(env_key)
    if "kurashift_re_vendor_list.yaml" not in written:
        raise SystemExit(
            "S2 YAML 必須。Secrets に KURASHIFT_RE_VENDOR_LIST_B64 を設定するか "
            "config/kurashift_re_vendor_list.yaml を置け"
        )
    if missing:
        print(f"# warn missing secrets (lane skip可能): {', '.join(missing)}", file=sys.stderr)
    return written


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--apply", action="store_true", help="既定で apply（dry-run 以外）")
    ap.add_argument("--lane", default="all")
    ap.add_argument("--evening", action="store_true", help="日次 #report 相当")
    ap.add_argument("--daily-report", action="store_true")
    ap.add_argument("--force-report", action="store_true")
    ap.add_argument("--skip-sync", action="store_true")
    args = ap.parse_args()

    if _disabled():
        print("📎 vendor_outreach_stall GHA: disabled")
        return 0

    materialize_yamls()
    (REPO / ".jarvis_state").mkdir(parents=True, exist_ok=True)

    os.environ["JARVIS_VENDOR_OUTREACH_STALL_SKIP_REFILL"] = "1"

    cmd = [
        sys.executable,
        str(REPO / "scripts" / "jarvis_vendor_outreach_stall_runner.py"),
        "--lane",
        args.lane,
        "--skip-refill",
    ]
    if args.dry_run:
        cmd.append("--dry-run")
    else:
        cmd.append("--apply")
    if args.evening or args.daily_report:
        cmd.append("--evening")
    if args.force_report:
        cmd.append("--force-report")
    if args.skip_sync:
        cmd.append("--skip-sync")

    print(f"# run: {' '.join(cmd)}", file=sys.stderr)
    r = subprocess.run(cmd, cwd=str(REPO), env=os.environ.copy())
    return int(r.returncode)


if __name__ == "__main__":
    raise SystemExit(main())
