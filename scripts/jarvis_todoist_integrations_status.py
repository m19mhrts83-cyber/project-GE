#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Todoist 任意連携（Webhook / Calendar）— 状態表示とゲート.

Phase 5b。既定は無効。有効化は config/todoist_projects.yaml integrations.* と
明示依頼のみ。対外送信・無確認 close はしない。

  ~/selenium_env/venv/bin/python scripts/jarvis_todoist_integrations_status.py
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
YAML = REPO / "config" / "todoist_projects.yaml"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    try:
        import yaml  # type: ignore
    except ImportError:
        print("ERROR: PyYAML required", file=sys.stderr)
        return 2
    data = yaml.safe_load(YAML.read_text(encoding="utf-8")) or {}
    integ = data.get("integrations") or {}
    wh = integ.get("webhook") or {}
    cal = integ.get("calendar_sync") or {}
    lines = [
        "📎 Todoist 任意連携（Phase5b）",
        f"- webhook: {'ON' if wh.get('enabled') else 'OFF（既定）'} — {wh.get('note') or ''}",
        f"- calendar_sync: {'ON' if cal.get('enabled') else 'OFF（既定）'} — {cal.get('note') or ''}",
        "- 予定正本は admin Googleカレンダー。Todoist Calendar レイアウトは UI 確認済。",
        "- Webhook を使うときは Todoist App Console 登録＋本 yaml の enabled: true。",
    ]
    text = "\n".join(lines)
    if args.json:
        import json

        print(
            json.dumps(
                {"webhook": wh, "calendar_sync": cal},
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
