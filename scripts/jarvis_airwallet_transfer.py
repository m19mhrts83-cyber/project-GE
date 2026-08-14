#!/usr/bin/env python3
"""エアウォレット（COIN+）寄せアシスト — Wave2。

アプリ中心のため、Jarvis は手順・初回着金ゲート・SMS OTP 自動取得・監査を担い、
アプリ内のタップは最小ユーザー操作（またはミラーリング）とする。

  python scripts/jarvis_airwallet_transfer.py --preview
  python scripts/jarvis_airwallet_transfer.py --go --money-ops-id UUID
  python scripts/jarvis_airwallet_transfer.py --go --poll-sms   # SMS をポーリング（既定ON）
  python scripts/jarvis_airwallet_transfer.py --mark-arrival-proven --note 'SMBC着金OK'
  python scripts/jarvis_airwallet_transfer.py --complete --evidence completion_screen
  python scripts/jarvis_airwallet_transfer.py --fetch-sms-otp

初回着金証明ゲート: .jarvis_state/airwallet_arrival_proof.json
  proven 前の本額 Go は拒否（--allow-unproven または少額テストのみ可）。
秘密: AIRWALLET_PHONE / AIRWALLET_PASSWORD（任意）。チャットに出さない。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import webbrowser
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))

from car_loan.env_state import load_env  # noqa: E402
from jarvis_transfer_audit import (  # noqa: E402
    TransferLock,
    append_audit,
    assert_balance_keep,
    dest_mask,
    make_idempotency_key,
)
from jarvis_transfer_otp import NeedsUserOtp, OtpFetchError, fetch_otp  # noqa: E402

RAIL_ID = "mufg_airwallet"
AMOUNT_DEFAULT = 290_000
KEEP_FLOOR = 85_000
# proven 前に許可するテスト上限（円）
UNPROVEN_MAX_JPY = 1_000
PROOF_PATH = REPO / ".jarvis_state" / "airwallet_arrival_proof.json"
GUIDE_URL = "https://airwallet.jp"
COINPLUS_URL = "https://coinplus.jp"
MUFG_COIN_URL = "https://www.bk.mufg.jp/tsukau/coinplus/index.html"
SENDER_HINT = "エアウォレット|COIN|COIN+|認証|リクルート|ワンタイム"
OTP_CHANNEL = "sms_messages"


def _env(name: str) -> str:
    return (os.environ.get(name) or "").strip()


def _load_proof() -> dict[str, Any]:
    if not PROOF_PATH.is_file():
        return {"proven": False}
    try:
        return json.loads(PROOF_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"proven": False}


def _save_proof(data: dict[str, Any]) -> None:
    PROOF_PATH.parent.mkdir(parents=True, exist_ok=True)
    safe = {k: v for k, v in data.items() if k not in ("password", "otp", "code")}
    PROOF_PATH.write_text(json.dumps(safe, ensure_ascii=False, indent=2), encoding="utf-8")


def _dest() -> tuple[str, str, str]:
    branch = _env("PERSONAL_BANK_BRANCH_CODE")
    acct = _env("PERSONAL_BANK_ACCOUNT")
    return branch, acct, dest_mask(acct, branch)


def _assert_arrival_gate(*, amount: int, allow_unproven: bool) -> None:
    proof = _load_proof()
    if proof.get("proven"):
        return
    if allow_unproven:
        print("⚠️ 初回着金未証明だが --allow-unproven で続行", file=sys.stderr)
        return
    if amount <= UNPROVEN_MAX_JPY:
        print(
            f"📎 初回未証明のため少額テスト枠（≤{UNPROVEN_MAX_JPY:,}円）として続行",
            file=sys.stderr,
        )
        return
    raise SystemExit(
        "初回着金未証明のため本額 Go を拒否しました。"
        f" 少額（≤{UNPROVEN_MAX_JPY:,}）で出金→SMBC着金確認後に"
        " --mark-arrival-proven、または明示的に --allow-unproven。"
    )


def preview(*, amount: int, money_ops_id: str, balance: int | None) -> str:
    branch, acct, dmask = _dest()
    key = make_idempotency_key(money_ops_id or "noid", RAIL_ID, amount, dmask)
    proof = _load_proof()
    print("=== 送金アシスト Preview (mufg_airwallet) / Wave2 ===")
    print("経路: 登録口座 → エアウォレット(COIN+) チャージ → SMBC刈谷へ出金")
    print("  ※千景名義 MUFG豊明は真治AWに紐づけ不可。真治名義口座＋刈谷向け。")
    print(f"金額目安: {amount:,}円 / keep下限目安: {KEEP_FLOOR:,}円")
    print(f"出金先: 三井住友銀行 刈谷 普通 {dmask}")
    print(f"otp_channel: {OTP_CHANNEL}（取得できれば Jarvis が自動。値はログに出さない）")
    print("役割分担:")
    print("  Jarvis: 手順・初回着金ゲート・SMS OTP取得・監査・完了証跡")
    print("  あなた: エアウォレットアプリのタップ／生体（必要最小限）")
    print(
        f"初回着金証明: {'✅ proven' if proof.get('proven') else '❌ 未（少額テスト→--mark-arrival-proven）'}"
    )
    if proof.get("proven_at"):
        print(f"  proven_at: {proof.get('proven_at')}")
    print(f"idempotency_key: {key}")
    if balance is not None:
        assert_balance_keep(balance, KEEP_FLOOR, amount)
        print("balance_keep: OK")
    append_audit(
        {
            "rail_id": RAIL_ID,
            "status": "previewed",
            "amount_jpy": amount,
            "dest_mask": dmask,
            "otp_channel": OTP_CHANNEL,
            "money_ops_id": money_ops_id or None,
            "idempotency_key": key,
            "arrival_proven": bool(proof.get("proven")),
            "wave": "2",
        }
    )
    return key


def print_playbook(*, amount: int, first: bool) -> None:
    print("--- 手順カード（アプリ）---")
    print("1. エアウォレットアプリを開く（未DLなら App Store / Google Play）")
    print("2. ログイン（電話番号+PW）。SMS 2段階なら Jarvis が Messages から自動取得")
    print("3. チャージ: 紐づけ済み口座から " + f"{amount:,}円")
    print("4. 出金: 三井住友銀行 刈谷（Olive引落口座）へ（≤10万は即時）")
    if first:
        print("5. 【初回】少額でもよいので SMBC 着金を確認 →")
        print("   python scripts/jarvis_airwallet_transfer.py --mark-arrival-proven")
    else:
        print("5. 完了後: --complete --evidence completion_screen|smbc_credit")
    print("ガイド:", GUIDE_URL)


def mark_proven(*, note: str, amount: int | None) -> None:
    _, _, dmask = _dest()
    data = {
        "proven": True,
        "proven_at": datetime.now(timezone.utc).isoformat(),
        "dest_mask": dmask,
        "note": (note or "")[:200],
        "amount_jpy_first": amount,
    }
    _save_proof(data)
    append_audit(
        {
            "rail_id": RAIL_ID,
            "status": "arrival_proven",
            "dest_mask": dmask,
            "evidence": "user_marked_arrival_proven",
            "amount_jpy": amount,
            "note": data["note"] or None,
            "wave": "2",
        }
    )
    print(f"✅ 初回着金証明を記録しました → {PROOF_PATH}")


def mark_complete(*, amount: int, money_ops_id: str, evidence: str) -> None:
    """done は証跡必須（completion_screen / smbc_credit / source_debit）。"""
    allowed = {"completion_screen", "smbc_credit", "source_debit"}
    if evidence not in allowed:
        raise SystemExit(f"--evidence は {sorted(allowed)} のいずれか")
    _, _, dmask = _dest()
    append_audit(
        {
            "rail_id": RAIL_ID,
            "status": "done",
            "amount_jpy": amount,
            "dest_mask": dmask,
            "evidence": evidence,
            "money_ops_id": money_ops_id or None,
            "otp_channel": OTP_CHANNEL,
            "wave": "2",
        }
    )
    print(f"✅ done evidence={evidence}")


def fetch_sms(*, timeout_sec: int = 90) -> int:
    try:
        code = fetch_otp(
            otp_channel=OTP_CHANNEL,
            rail_id=RAIL_ID,
            sender_hint=SENDER_HINT,
            timeout_sec=timeout_sec,
        )
    except NeedsUserOtp:
        print("otp_status=needs_user", file=sys.stderr)
        return 2
    except OtpFetchError as e:
        print(f"otp_status=failed reason={e}", file=sys.stderr)
        return 1
    print("otp_status=ok otp_obtained=true", file=sys.stderr)
    if code:
        sys.stdout.write(code)
        sys.stdout.flush()
    append_audit(
        {
            "rail_id": RAIL_ID,
            "status": "otp_submit",
            "otp_channel": OTP_CHANNEL,
            "otp_obtained": True,
            "wave": "2",
        }
    )
    return 0


def run_go(
    *,
    amount: int,
    money_ops_id: str,
    balance: int | None,
    open_urls: bool,
    poll_sms: bool,
    allow_unproven: bool,
) -> int:
    _assert_arrival_gate(amount=amount, allow_unproven=allow_unproven)
    key = preview(amount=amount, money_ops_id=money_ops_id, balance=balance)
    proof = _load_proof()
    _, _, dmask = _dest()
    lock = TransferLock(key)
    if not lock.acquire():
        print("lock_busy", file=sys.stderr)
        return 3
    try:
        append_audit(
            {
                "rail_id": RAIL_ID,
                "status": "running",
                "amount_jpy": amount,
                "dest_mask": dmask,
                "otp_channel": OTP_CHANNEL,
                "money_ops_id": money_ops_id or None,
                "idempotency_key": key,
                "wave": "2",
            }
        )
        first = not bool(proof.get("proven"))
        print_playbook(amount=amount, first=first)
        if open_urls:
            for u in (GUIDE_URL, MUFG_COIN_URL):
                try:
                    webbrowser.open(u)
                except Exception:
                    pass

        otp_ok = False
        if poll_sms:
            print("📎 SMS OTP をポーリング中（取れなければアプリ生体／手動）…", file=sys.stderr)
            append_audit(
                {
                    "rail_id": RAIL_ID,
                    "status": "otp_fetch",
                    "otp_channel": OTP_CHANNEL,
                    "amount_jpy": amount,
                    "wave": "2",
                }
            )
            try:
                code = fetch_otp(
                    otp_channel=OTP_CHANNEL,
                    rail_id=RAIL_ID,
                    sender_hint=SENDER_HINT,
                    timeout_sec=90,
                )
                if code:
                    otp_ok = True
                    # 値は stdout のみ（ミラーリング入力用）。stderr には出さない
                    print("otp_status=ok otp_obtained=true", file=sys.stderr)
                    print(
                        "📎 OTP取得済 → iPhoneミラーリング等で入力欄へ貼り付け可（値は再掲しません）",
                        file=sys.stderr,
                    )
                    sys.stdout.write(code + "\n")
                    sys.stdout.flush()
                    append_audit(
                        {
                            "rail_id": RAIL_ID,
                            "status": "otp_submit",
                            "otp_channel": OTP_CHANNEL,
                            "otp_obtained": True,
                            "wave": "2",
                        }
                    )
            except (NeedsUserOtp, OtpFetchError) as e:
                print(f"otp_status=deferred reason={e}", file=sys.stderr)
                append_audit(
                    {
                        "rail_id": RAIL_ID,
                        "status": "otp_fetch",
                        "otp_channel": OTP_CHANNEL,
                        "otp_obtained": False,
                        "error": "otp_deferred",
                        "wave": "2",
                    }
                )

        append_audit(
            {
                "rail_id": RAIL_ID,
                "status": "waiting_user",
                "amount_jpy": amount,
                "dest_mask": dmask,
                "otp_channel": OTP_CHANNEL,
                "otp_obtained": otp_ok,
                "error": "awaiting_app_taps",
                "arrival_proven": not first,
                "wave": "2",
            }
        )
        print("👉 アプリ操作が終わったら:")
        print("   python scripts/jarvis_airwallet_transfer.py --complete --evidence smbc_credit")
        if first:
            print("   初回なら先に --mark-arrival-proven")
        return 0
    finally:
        lock.release()


def main() -> int:
    load_env()
    p = argparse.ArgumentParser(description="エアウォレット寄せ Wave2")
    p.add_argument("--preview", action="store_true")
    p.add_argument("--go", action="store_true")
    p.add_argument("--mark-arrival-proven", action="store_true")
    p.add_argument("--complete", action="store_true", help="証跡付き done")
    p.add_argument(
        "--evidence",
        default="completion_screen",
        help="completion_screen|smbc_credit|source_debit",
    )
    p.add_argument("--fetch-sms-otp", action="store_true")
    p.add_argument("--open", action="store_true", help="ガイドURLを開く")
    p.add_argument(
        "--poll-sms",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Go 時に SMS OTP を自動ポーリング（既定: on）",
    )
    p.add_argument(
        "--allow-unproven",
        action="store_true",
        help="初回着金未証明でも本額 Go を許可（非推奨）",
    )
    p.add_argument("--money-ops-id", default="")
    p.add_argument("--amount", type=int, default=AMOUNT_DEFAULT)
    p.add_argument("--balance", type=int, default=None)
    p.add_argument("--note", default="")
    args = p.parse_args()
    if args.mark_arrival_proven:
        mark_proven(note=args.note, amount=args.amount)
        return 0
    if args.complete:
        mark_complete(
            amount=args.amount,
            money_ops_id=args.money_ops_id,
            evidence=args.evidence,
        )
        return 0
    if args.fetch_sms_otp:
        return fetch_sms()
    if args.preview and not args.go:
        preview(amount=args.amount, money_ops_id=args.money_ops_id, balance=args.balance)
        print_playbook(amount=args.amount, first=not _load_proof().get("proven"))
        return 0
    if args.go:
        return run_go(
            amount=args.amount,
            money_ops_id=args.money_ops_id,
            balance=args.balance,
            open_urls=args.open,
            poll_sms=bool(args.poll_sms),
            allow_unproven=bool(args.allow_unproven),
        )
    if args.open:
        webbrowser.open(GUIDE_URL)
        return 0
    p.error(
        "--preview / --go / --mark-arrival-proven / --complete / --fetch-sms-otp が必要です"
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
