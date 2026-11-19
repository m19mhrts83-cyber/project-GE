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

Supabase 上書き（2026-11-19）:
  RE 台帳は gzip 後も約87KB で Secret 上限（48KB）に入らず、Secret が 10/15 のまま
  深夜の報告が「S2 直近7日0件・最終10/7」と古い数値を出していた。
  Mac が毎回 Supabase（kurashift_re_vendors / _mgmt_vendors / _repair_vendors）へ投影して
  いるので、Secret（settings・バッチ等の土台）を展開したあと、業者ごとの状態列
  （status・contacted_at・replied_at など）を Supabase の行で上書きし、Secret に無い業者は足す。
  Secret が無くても Supabase だけで動く（settings は空＝既定値）。
  止める: JARVIS_VENDOR_STALL_SUPABASE_OVERLAY=0
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


SUPABASE_TABLES = {
    "kurashift_re_vendor_list.yaml": "kurashift_re_vendors",
    "kurashift_mgmt_vendor_list.yaml": "kurashift_re_mgmt_vendors",
    "kurashift_repair_vendor_list.yaml": "kurashift_re_repair_vendors",
}
# 台帳側で正本が Mac の YAML にあり、Supabase には投影だけの列。上書きしない
_SKIP_OVERLAY_KEYS = {"synced_at", "updated_at"}


def _overlay_enabled() -> bool:
    return (os.environ.get("JARVIS_VENDOR_STALL_SUPABASE_OVERLAY") or "1").strip().lower() not in (
        "0", "false", "no", "off",
    )


def overlay_vendors(data: dict, rows: list[dict]) -> dict:
    """Secret 由来の台帳に Supabase の行を重ねる（行の値を優先・None は上書きしない）。"""
    data = dict(data or {})
    data.setdefault("settings", {})
    vendors = [v for v in (data.get("vendors") or []) if isinstance(v, dict)]
    by_id = {str(v.get("id")): v for v in vendors if v.get("id")}
    for r in rows:
        vid = str(r.get("id") or "")
        if not vid:
            continue
        fields = {k: v for k, v in r.items() if k not in _SKIP_OVERLAY_KEYS and v is not None}
        if vid in by_id:
            by_id[vid].update(fields)
        else:
            nv = dict(fields)
            vendors.append(nv)
            by_id[vid] = nv
    data["vendors"] = vendors
    return data


def _fetch_rows(sb, table: str) -> list[dict]:
    out: list[dict] = []
    step = 1000
    start = 0
    while True:
        res = sb.table(table).select("*").range(start, start + step - 1).execute()
        batch = res.data or []
        out.extend(batch)
        if len(batch) < step:
            return out
        start += step


def overlay_from_supabase(cfg: Path) -> list[str]:
    """Supabase の業者表で YAML を最新化する。失敗しても Secret のまま進める（soft-fail）。"""
    if not _overlay_enabled():
        print("# supabase overlay: disabled", file=sys.stderr)
        return []
    url = os.environ.get("JARVIS_SUPABASE_URL")
    key = os.environ.get("JARVIS_SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        print("# supabase overlay: skip (no JARVIS_SUPABASE_*)", file=sys.stderr)
        return []
    try:
        import yaml
        from supabase import create_client

        sb = create_client(url, key)
    except Exception as e:  # noqa: BLE001
        print(f"::warning::supabase overlay: client failed: {e}", file=sys.stderr)
        return []
    done: list[str] = []
    for name, table in SUPABASE_TABLES.items():
        dest = cfg / name
        try:
            rows = _fetch_rows(sb, table)
        except Exception as e:  # noqa: BLE001
            print(f"::warning::supabase overlay: {table} read failed: {e}", file=sys.stderr)
            continue
        if not rows:
            print(f"# supabase overlay: {table} empty → keep", file=sys.stderr)
            continue
        base = yaml.safe_load(dest.read_text(encoding="utf-8")) if dest.is_file() else {}
        merged = overlay_vendors(base or {}, rows)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(yaml.safe_dump(merged, allow_unicode=True, sort_keys=False), encoding="utf-8")
        latest = max((str(r.get("synced_at") or "") for r in rows), default="")
        print(f"# supabase overlay: {name} ← {table} {len(rows)} rows (synced_at max {latest[:19]})",
              file=sys.stderr)
        done.append(name)
    return done


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
    for name in overlay_from_supabase(cfg):
        if name not in written:
            written.append(name)
    if "kurashift_re_vendor_list.yaml" not in written:
        raise SystemExit(
            "S2 YAML 必須。Supabase の kurashift_re_vendors を読めず、"
            "Secret KURASHIFT_RE_VENDOR_LIST_B64 も config/kurashift_re_vendor_list.yaml も無い"
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
