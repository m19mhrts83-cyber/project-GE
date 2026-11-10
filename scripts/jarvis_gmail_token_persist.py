#!/usr/bin/env python3
"""Gmail token の保存口（2026-11-10）。

refresh 後に creds.to_json() をそのまま書くと、読み込み時に渡した狭いスコープ
（readonly だけ等）で token の scopes 記録が上書きされ、Google 側では送信の許可が
生きているのに「送信は要再同意」と判定され続ける（毎朝 5:01 の再発原因）。

保存は必ずここを通し、既存 token の gmail.* スコープ（特に send）を落とさない。
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
MANUAL = REPO / "215_kamiooya" / "C1_cursor" / "1b_Cursorマニュアル"
if str(MANUAL) not in sys.path:
    sys.path.insert(0, str(MANUAL))

from gmail_api_scopes import merge_gmail_scopes_for_persist  # noqa: E402


def save_gmail_token(path: Path | str, creds: Any) -> None:
    """creds を path に保存する。既存の gmail.* スコープ記録は残す。"""
    p = Path(path)
    text = merge_gmail_scopes_for_persist(creds.to_json(), existing_token_path=p)
    p.write_text(text, encoding="utf-8")
