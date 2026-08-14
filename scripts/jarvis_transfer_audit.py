#!/usr/bin/env python3
"""送金アシスト — 監査ログと idempotency ロック。

秘密（PW / OTP 値 / 口座全文）は絶対に書かない。
"""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
AUDIT_DIR = REPO / ".jarvis_state" / "transfer_audit"
LOCK_DIR = REPO / ".jarvis_state" / "transfer_locks"


def dest_mask(account: str | None, branch: str | None = None) -> str:
    acct = re.sub(r"\D", "", account or "")
    br = re.sub(r"\D", "", branch or "")
    last4 = acct[-4:] if len(acct) >= 4 else "????"
    return f"br{br or '???'}_…{last4}"


def make_idempotency_key(
    money_ops_id: str,
    rail_id: str,
    amount_jpy: int,
    dest_mask_s: str,
) -> str:
    mid = re.sub(r"[^a-zA-Z0-9_-]", "", money_ops_id or "noid")[:64]
    rid = re.sub(r"[^a-zA-Z0-9_-]", "", rail_id or "rail")[:64]
    return f"{mid}:{rid}:{int(amount_jpy)}:{dest_mask_s}"


def _safe_event(event: dict[str, Any]) -> dict[str, Any]:
    banned = (
        "password",
        "pass",
        "otp",
        "code",
        "token",
        "account_full",
        "secret",
        "合言葉",
    )
    out: dict[str, Any] = {}
    for k, v in event.items():
        lk = str(k).lower()
        if any(b in lk for b in banned) and k not in (
            "otp_channel",
            "otp_obtained",
        ):
            continue
        if isinstance(v, str) and len(v) > 500:
            out[k] = v[:500] + "…"
        else:
            out[k] = v
    return out


def append_audit(event: dict[str, Any]) -> Path:
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    day = datetime.now(timezone.utc).strftime("%Y%m%d")
    path = AUDIT_DIR / f"{day}.jsonl"
    row = {
        "ts": datetime.now(timezone.utc).isoformat(),
        **_safe_event(event),
    }
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
    return path


class TransferLock:
    """同一 idempotency_key の二重 running を防ぐ。"""

    def __init__(self, key: str):
        self.key = key
        safe = re.sub(r"[^a-zA-Z0-9:_-]", "_", key)[:180]
        LOCK_DIR.mkdir(parents=True, exist_ok=True)
        self.path = LOCK_DIR / f"{safe}.lock"
        self._fh: Any = None

    def acquire(self, *, blocking: bool = False) -> bool:
        self._fh = open(self.path, "a+", encoding="utf-8")
        try:
            flags = fcntl.LOCK_EX
            if not blocking:
                flags |= fcntl.LOCK_NB
            fcntl.flock(self._fh.fileno(), flags)
        except BlockingIOError:
            self._fh.close()
            self._fh = None
            return False
        self._fh.seek(0)
        self._fh.truncate()
        self._fh.write(
            json.dumps(
                {
                    "key": self.key,
                    "pid": os.getpid(),
                    "acquired_at": time.time(),
                }
            )
        )
        self._fh.flush()
        return True

    def release(self) -> None:
        if self._fh is None:
            return
        try:
            fcntl.flock(self._fh.fileno(), fcntl.LOCK_UN)
        finally:
            self._fh.close()
            self._fh = None

    def __enter__(self) -> "TransferLock":
        if not self.acquire():
            raise RuntimeError(f"lock_busy:{self.key}")
        return self

    def __exit__(self, *args: object) -> None:
        self.release()


def assert_amount_triple(
    plan_amount: int | None,
    cli_amount: int | None,
    confirm_amount: int | None,
) -> None:
    amounts = [plan_amount, cli_amount, confirm_amount]
    known = [a for a in amounts if a is not None]
    if len(known) < 2:
        return
    if len(set(int(a) for a in known)) != 1:
        raise ValueError(
            f"amount_mismatch plan={plan_amount} cli={cli_amount} confirm={confirm_amount}"
        )


def assert_balance_keep(
    balance_jpy: int | None,
    keep_floor_jpy: int | None,
    amount_jpy: int,
) -> None:
    if balance_jpy is None or keep_floor_jpy is None:
        return
    if int(balance_jpy) - int(keep_floor_jpy) < int(amount_jpy):
        raise ValueError(
            f"balance_keep_guard balance={balance_jpy} keep={keep_floor_jpy} amount={amount_jpy}"
        )


def main() -> int:
    p = argparse.ArgumentParser(description="transfer audit / lock helper")
    sub = p.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("append")
    a.add_argument("--rail-id", required=True)
    a.add_argument("--status", required=True)
    a.add_argument("--amount", type=int)
    a.add_argument("--dest-mask", default="")
    a.add_argument("--otp-channel", default="")
    a.add_argument("--otp-obtained", choices=["true", "false", ""])
    a.add_argument("--money-ops-id", default="")
    a.add_argument("--evidence", default="")
    a.add_argument("--error", default="")

    k = sub.add_parser("key")
    k.add_argument("--money-ops-id", required=True)
    k.add_argument("--rail-id", required=True)
    k.add_argument("--amount", type=int, required=True)
    k.add_argument("--dest-mask", required=True)

    args = p.parse_args()
    if args.cmd == "key":
        print(
            make_idempotency_key(
                args.money_ops_id, args.rail_id, args.amount, args.dest_mask
            )
        )
        return 0

    ev: dict[str, Any] = {
        "rail_id": args.rail_id,
        "status": args.status,
        "money_ops_id": args.money_ops_id or None,
    }
    if args.amount is not None:
        ev["amount_jpy"] = args.amount
    if args.dest_mask:
        ev["dest_mask"] = args.dest_mask
    if args.otp_channel:
        ev["otp_channel"] = args.otp_channel
    if args.otp_obtained:
        ev["otp_obtained"] = args.otp_obtained == "true"
    if args.evidence:
        ev["evidence"] = args.evidence
    if args.error:
        # メッセージのみ。秘密を入れない前提。
        ev["error"] = args.error[:200]
    path = append_audit(ev)
    print(f"audit_appended={path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
