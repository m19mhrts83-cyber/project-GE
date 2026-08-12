#!/usr/bin/env python3
"""KURASHIFT: .env.jarvis_private への許可キー追記／設定状況（値は出さない）。

  python scripts/jarvis_kurashift_secrets.py --status
  python scripts/jarvis_kurashift_secrets.py --upsert-json '{"BLOOMO_EMAIL":"x"}'
  # worker からは --upsert-file /tmp/….json（成功後に削除）
"""
from __future__ import annotations

import argparse
import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
ENV_PATH = REPO / ".env.jarvis_private"

# アプリ設定から書き込んでよいキーのみ（ホワイトリスト）
ALLOWED_KEYS = {
    "SONYLIFE_LOGIN_URL",
    "SONYLIFE_USERNAME",
    "SONYLIFE_PASSWORD",
    "SONYLIFE_USERNAME_1",
    "SONYLIFE_PASSWORD_1",
    "SONYLIFE_USERNAME_2",
    "SONYLIFE_PASSWORD_2",
    "BLOOMO_LOGIN_URL",
    "BLOOMO_EMAIL",
    "BLOOMO_PASSWORD",
    "PRUDENTIAL_LOGIN_URL",
    "PRUDENTIAL_USERNAME",
    "PRUDENTIAL_PASSWORD",
    "PRUDENTIAL_USERNAME_1",
    "PRUDENTIAL_PASSWORD_1",
    "PRUDENTIAL_USERNAME_2",
    "PRUDENTIAL_PASSWORD_2",
    "PRUDENTIAL_VALUE_JPY",
    "PRUDENTIAL_CHIKAGE_VALUE_JPY",
    "PRUDENTIAL_LOAN_JPY",
    "PRUDENTIAL_CHIKAGE_LOAN_JPY",
    "AKATSUKI_BRANCH_CODE",
    "AKATSUKI_ACCOUNT_NUMBER",
    "AKATSUKI_LOGIN_PASSWORD",
    "SBI_SEC_USER",
    "SBI_SEC_LOGIN_PASSWORD",
    "AXA_MYAXA_ID",
    "AXA_MYAXA_PASSWORD",
}

KEY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def emit_result(obj: dict[str, Any]) -> None:
    print("KURASHIFT_RESULT:" + json.dumps(obj, ensure_ascii=False))


def parse_env_file(path: Path) -> list[str]:
    if not path.is_file():
        return []
    return path.read_text(encoding="utf-8").splitlines()


def key_set_map(lines: list[str]) -> dict[str, bool]:
    present: dict[str, bool] = {k: False for k in sorted(ALLOWED_KEYS)}
    for line in lines:
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        k, v = s.split("=", 1)
        k = k.strip()
        if k in present and v.strip().strip("'\""):
            present[k] = True
    return present


def upsert_keys(updates: dict[str, str]) -> dict[str, Any]:
    clean: dict[str, str] = {}
    rejected: list[str] = []
    for k, v in updates.items():
        if k not in ALLOWED_KEYS or not KEY_RE.match(k):
            rejected.append(k)
            continue
        val = str(v).strip()
        if not val:
            continue
        # 改行・制御文字を落とす
        val = val.replace("\n", "").replace("\r", "")
        clean[k] = val

    lines = parse_env_file(ENV_PATH)
    seen: set[str] = set()
    out_lines: list[str] = []
    for line in lines:
        s = line.strip()
        if s and not s.startswith("#") and "=" in s:
            k = s.split("=", 1)[0].strip()
            if k in clean:
                out_lines.append(f"{k}={clean[k]}")
                seen.add(k)
                continue
        out_lines.append(line)

    added: list[str] = []
    if clean:
        if out_lines and out_lines[-1].strip():
            out_lines.append("")
        out_lines.append(f"# KURASHIFT settings upsert {now_iso()}")
        for k, v in clean.items():
            if k not in seen:
                out_lines.append(f"{k}={v}")
                added.append(k)

    ENV_PATH.parent.mkdir(parents=True, exist_ok=True)
    # 原子的に書く
    fd, tmp = tempfile.mkstemp(
        prefix=".env.jarvis_private.", dir=str(ENV_PATH.parent)
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write("\n".join(out_lines).rstrip() + "\n")
        os.chmod(tmp, 0o600)
        os.replace(tmp, ENV_PATH)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise

    status = key_set_map(parse_env_file(ENV_PATH))
    return {
        "action": "secrets_upsert",
        "updated": sorted(clean.keys()),
        "added": added,
        "rejected": rejected,
        "status": status,
        "path": str(ENV_PATH.name),
    }


def write_sync_meta(status: dict[str, bool]) -> None:
    url = os.environ.get("JARVIS_SUPABASE_URL")
    key = os.environ.get("JARVIS_SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        return
    try:
        from supabase import create_client

        sb = create_client(url, key)
        ts = now_iso()
        sb.table("sync_meta").upsert(
            [
                {
                    "key": "kurashift_secrets_status",
                    "value": json.dumps(status, ensure_ascii=False),
                    "updated_at": ts,
                },
                {
                    "key": "kurashift_secrets_updated_at",
                    "value": ts,
                    "updated_at": ts,
                },
            ],
            on_conflict="key",
        ).execute()
    except Exception as exc:  # noqa: BLE001
        print(f"# sync_meta skip: {exc}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--upsert-json", default="")
    ap.add_argument("--upsert-file", default="")
    ap.add_argument("--no-sync-meta", action="store_true")
    args = ap.parse_args()

    if args.status:
        status = key_set_map(parse_env_file(ENV_PATH))
        out = {"action": "secrets_status", "status": status, "set_count": sum(1 for v in status.values() if v)}
        print(json.dumps(out, ensure_ascii=False, indent=2))
        emit_result(out)
        if not args.no_sync_meta:
            write_sync_meta(status)
        return 0

    updates: dict[str, str] = {}
    if args.upsert_file:
        p = Path(args.upsert_file)
        data = json.loads(p.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            updates = {str(k): str(v) for k, v in data.items()}
        try:
            p.unlink()
        except OSError:
            pass
    elif args.upsert_json:
        data = json.loads(args.upsert_json)
        if isinstance(data, dict):
            updates = {str(k): str(v) for k, v in data.items()}
    else:
        raise SystemExit("specify --status | --upsert-json | --upsert-file")

    out = upsert_keys(updates)
    # 値は絶対に出さない
    print(
        json.dumps(
            {
                "action": out["action"],
                "updated": out["updated"],
                "added": out["added"],
                "rejected": out["rejected"],
                "set_count": sum(1 for v in out["status"].values() if v),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    emit_result(
        {
            "action": out["action"],
            "updated": out["updated"],
            "added": out["added"],
            "rejected": out["rejected"],
            "set_count": sum(1 for v in out["status"].values() if v),
        }
    )
    if not args.no_sync_meta:
        write_sync_meta(out["status"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
