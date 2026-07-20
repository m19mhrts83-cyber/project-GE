#!/usr/bin/env python3
"""
Phase 0: Square API 401 復旧の技術検証（device / app version / CHRLINE 版）。

各構成で QR ログイン（--allow-qr-login）→ fetchSquareChatEvents 1 回。
結果は ~/.jarvis_state/square_probe.json に追記。

使い方:
  cd ~/git-repos/line_unofficial_poc  # 正本
  .venv/bin/python chrline_square_probe_phase0.py --allow-qr-login
  .venv/bin/python chrline_square_probe_phase0.py --allow-qr-login --device CHROMEOS
  .venv/bin/python chrline_square_probe_phase0.py --allow-qr-login --all-presets
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from chrline_client_utils import (
    DEFAULT_CHRLINE_APP_VERSION,
    DEFAULT_CHRLINE_DEVICE,
    DEFAULT_SQUARE_PROBE_MID,
    build_logged_in_client,
    chrline_app_version_from_env,
    chrline_device_from_env,
    clear_process_client_cache,
    probe_square_session_detail,
    save_root_from_env,
)

STATE_PATH = Path.home() / "git-repos" / ".jarvis_state" / "square_probe.json"

PHASE0_PRESETS: list[dict[str, str]] = [
    {"label": "default_desktopwin", "device": "DESKTOPWIN", "app_version": DEFAULT_CHRLINE_APP_VERSION},
    {"label": "chromeos", "device": "CHROMEOS", "app_version": DEFAULT_CHRLINE_APP_VERSION},
    {"label": "android_secondary", "device": "ANDROIDSECONDARY", "app_version": DEFAULT_CHRLINE_APP_VERSION},
    {"label": "desktopwin_newer_app", "device": "DESKTOPWIN", "app_version": "14.0.0.3360"},
]


def _load_state() -> dict[str, Any]:
    if STATE_PATH.is_file():
        try:
            return json.loads(STATE_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {"history": [], "last_ok": None, "structural_limit": False}


def _save_state(state: dict[str, Any]) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _run_one_preset(
    preset: dict[str, str],
    *,
    save_root: Path,
    allow_qr_login: bool,
    square_mid: str,
) -> dict[str, Any]:
    os.environ["LINE_CHRLINE_DEVICE"] = preset["device"]
    os.environ["LINE_CHRLINE_APP_VERSION"] = preset["app_version"]
    clear_process_client_cache(save_root)
    cl = build_logged_in_client(save_root, allow_qr_login=allow_qr_login)
    detail = probe_square_session_detail(cl, square_chat_mid=square_mid)
    detail["preset"] = preset["label"]
    detail["chrline_package"] = _chrline_version()
    detail["at"] = datetime.now(timezone.utc).isoformat()
    return detail


def _chrline_version() -> str:
    try:
        import importlib.metadata as im

        return im.version("CHRLINE")
    except Exception:
        return "unknown"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Square API Phase 0 疎通検証")
    parser.add_argument("--allow-qr-login", action="store_true", help="トークン無効時 QR 再認証")
    parser.add_argument("--device", default="", help="単体テスト用 device（未指定時は env または DESKTOPWIN）")
    parser.add_argument("--app-version", default="", help="単体テスト用 LINE_CHRLINE_APP_VERSION")
    parser.add_argument("--all-presets", action="store_true", help="PHASE0_PRESETS を順に試す（各 preset で QR 要）")
    parser.add_argument(
        "--square-mid",
        default=DEFAULT_SQUARE_PROBE_MID,
        help="fetchSquareChatEvents テスト用 square_chat_mid",
    )
    args = parser.parse_args(argv)
    save_root = save_root_from_env()
    state = _load_state()
    results: list[dict[str, Any]] = []

    if args.all_presets:
        presets = PHASE0_PRESETS
    elif args.device or args.app_version:
        presets = [
            {
                "label": "custom",
                "device": args.device or chrline_device_from_env(),
                "app_version": args.app_version or chrline_app_version_from_env(),
            }
        ]
    else:
        presets = [PHASE0_PRESETS[0]]

    any_ok = False
    for i, preset in enumerate(presets):
        if i > 0:
            print(
                f"# Phase0: 次 preset={preset['label']}（device={preset['device']}）— QR 承認が必要な場合があります",
                file=sys.stderr,
            )
        detail = _run_one_preset(
            preset,
            save_root=save_root,
            allow_qr_login=args.allow_qr_login,
            square_mid=args.square_mid.strip(),
        )
        results.append(detail)
        ok = bool(detail.get("ok"))
        any_ok = any_ok or ok
        print(
            f"# Phase0 [{preset['label']}]: ok={ok} main={detail.get('main_ok')} "
            f"thread={detail.get('thread_ok')} device={detail.get('device')} "
            f"version={detail.get('app_version')} error={detail.get('error', '')[:80]}",
            file=sys.stderr,
        )
        if ok:
            break

    state["history"] = (state.get("history") or [])[-49:] + results
    if any_ok:
        state["last_ok"] = results[-1]
        state["structural_limit"] = False
    else:
        state["structural_limit"] = len(presets) >= len(PHASE0_PRESETS) or args.all_presets
    state["last_run_at"] = datetime.now(timezone.utc).isoformat()
    _save_state(state)

    print(f"# Phase0 結果: any_ok={any_ok} state={STATE_PATH}", file=sys.stderr)
    if state.get("structural_limit") and not any_ok:
        print("# Phase0 判定: 構造限界（Square API 401 継続）→ Phase 1 運用切替", file=sys.stderr)
        return 1
    return 0 if any_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
