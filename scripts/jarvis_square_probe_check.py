#!/usr/bin/env python3
"""
Square API プローブ結果の読取・軽量再チェック（Phase 2 復活監視）。

パートナー確認のオプチャフェーズ前後で state を更新し、報告ブロックを stdout に出す。

使い方:
  cd ~/git-repos && selenium_env/venv/bin/python scripts/jarvis_square_probe_check.py
  cd ~/git-repos && selenium_env/venv/bin/python scripts/jarvis_square_probe_check.py --probe --allow-qr-login
  cd ~/git-repos && selenium_env/venv/bin/python scripts/jarvis_square_probe_check.py --mark-probed
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
LINE_POC = REPO / "line_unofficial_poc"
STATE_PATH = REPO / ".jarvis_state" / "square_probe.json"
EXAMPLE_PATH = REPO / ".jarvis_state" / "square_probe.example.json"


def _load_state() -> dict:
    if STATE_PATH.is_file():
        try:
            return json.loads(STATE_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {"history": [], "last_ok": None, "structural_limit": True, "last_probe_at": None}


def _save_state(state: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _run_live_probe(*, allow_qr_login: bool) -> dict:
    sys.path.insert(0, str(LINE_POC))
    from chrline_client_utils import (
        build_logged_in_client,
        format_square_probe_report,
        probe_square_session_detail,
        save_root_from_env,
    )

    save_root = save_root_from_env()
    cl = build_logged_in_client(save_root, allow_qr_login=allow_qr_login)
    return probe_square_session_detail(cl)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Square probe state / 軽量チェック")
    parser.add_argument("--probe", action="store_true", help="ライブ fetchSquareChatEvents を1回実行")
    parser.add_argument("--allow-qr-login", action="store_true", help="--probe 時 QR 許可")
    parser.add_argument("--mark-probed", action="store_true", help="last_probe_at のみ更新（probe なし）")
    args = parser.parse_args(argv)

    state = _load_state()
    detail: dict | None = None

    if args.probe:
        detail = _run_live_probe(allow_qr_login=args.allow_qr_login)
        state["last_probe_at"] = datetime.now(timezone.utc).isoformat()
        state["last_probe"] = detail
        if detail.get("ok"):
            state["last_ok"] = detail
            state["structural_limit"] = False
        else:
            state["structural_limit"] = True
        hist = state.get("history") or []
        hist.append(detail)
        state["history"] = hist[-50:]
        _save_state(state)
        try:
            from jarvis_chrline_version_check import run_version_check

            run_version_check(force_upstream=False)
        except Exception:
            pass
    elif args.mark_probed:
        state["last_probe_at"] = datetime.now(timezone.utc).isoformat()
        _save_state(state)

    if detail is None and state.get("last_probe"):
        detail = state["last_probe"]

    if detail:
        sys.path.insert(0, str(LINE_POC))
        from chrline_client_utils import format_square_probe_report

        print(format_square_probe_report(detail))
        if not detail.get("ok"):
            try:
                sys.path.insert(0, str(REPO / "scripts"))
                from jarvis_chrline_version_check import (
                    format_version_report,
                    run_version_check,
                )

                ver = run_version_check(force_upstream=False)
                if ver.get("update_available") or ver.get("source_refresh_suggested"):
                    print(format_version_report(ver))
            except Exception:
                pass
    elif state.get("structural_limit"):
        print("---")
        print("📎 Square API プローブ（オープンチャット）")
        print("- 判定: 401/不可（構造限界フラグ ON・前回 Phase0 未復旧）")
        print("- オプチャ同期: スキップ推奨")
        print("---")

    return 0 if (detail or {}).get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
