#!/usr/bin/env python3
"""
定期実行用: 連続失敗カウントを管理し、閾値到達時のみLINEで失敗通知する。
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from akatsuki_bond_balance import DEFAULT_ENV_PATH, fetch_bond_balance
from notify_line_balance import send_balance_with_pl_to_line, send_text_to_line


DEFAULT_STATE_PATH = Path.home() / ".local" / "state" / "akatsuki_bond_balance_state.json"


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _load_state(path: Path) -> dict:
    if not path.exists():
        return {"consecutive_failures": 0, "last_alerted_failure_count": 0}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"consecutive_failures": 0, "last_alerted_failure_count": 0}


def _save_state(path: Path, state: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="定期実行: あかつき債券残高LINE通知")
    parser.add_argument("--headless", action="store_true", help="ヘッドレスでブラウザ実行")
    parser.add_argument("--timeout-ms", type=int, default=45000, help="Playwright タイムアウト（ms）")
    parser.add_argument("--save-debug", action="store_true", help="最終ページのHTML/PNGを保存")
    parser.add_argument("--env-file", default=str(DEFAULT_ENV_PATH), help="環境変数ファイル")
    parser.add_argument(
        "--state-file",
        default=str(DEFAULT_STATE_PATH),
        help="連続失敗カウント保存先（既定: ~/.local/state/akatsuki_bond_balance_state.json）",
    )
    parser.add_argument(
        "--failure-alert-threshold",
        type=int,
        default=int(os.environ.get("AKATSUKI_ALERT_FAILURE_THRESHOLD", "3")),
        help="連続失敗何回で通知するか（既定3）",
    )
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    state_path = Path(args.state_file).expanduser()
    state = _load_state(state_path)

    # 定期実行では勝手にQR再認証へ進まない（止まる/手動介入が必要になるため）
    os.environ["AKATSUKI_DISABLE_AUTO_QR_RETRY"] = "1"

    try:
        result = fetch_bond_balance(
            headless=args.headless,
            timeout_ms=args.timeout_ms,
            save_debug=args.save_debug,
            allow_bond_nav_skip=False,
            env_file=Path(args.env_file).expanduser(),
        )
        backend = send_balance_with_pl_to_line(
            eval_jpy=result.total_jpy,
            pl_jpy=result.pl_jpy,
            category=result.category,
            allow_qr_login=False,
        )
        state["consecutive_failures"] = 0
        state["last_alerted_failure_count"] = 0
        state["last_success_at"] = _now_iso()
        state["last_total_jpy"] = result.total_jpy
        state["last_notify_backend"] = backend
        _save_state(state_path, state)
        print(f"OK: 債券残高合計 {result.total_jpy:,}円 ({backend})")
        return 0
    except Exception as exc:
        count = int(state.get("consecutive_failures", 0)) + 1
        state["consecutive_failures"] = count
        state["last_error"] = str(exc)
        state["last_failed_at"] = _now_iso()

        threshold = max(1, int(args.failure_alert_threshold))
        alerted = int(state.get("last_alerted_failure_count", 0))
        should_alert = count >= threshold and alerted < threshold
        if should_alert:
            fail_msg = (
                f"あかつき債券残高通知: {count}回連続で失敗しています。"
                f"原因: {str(exc)[:200]}"
            )
            try:
                send_text_to_line(fail_msg, allow_qr_login=False)
                state["last_alerted_failure_count"] = threshold
            except Exception as alert_exc:
                state["last_alert_error"] = str(alert_exc)
        _save_state(state_path, state)
        print(f"NG: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
