#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""リポジトリルートからの入口。本体はチャットボット scripts 側。"""

from __future__ import annotations

import runpy
from pathlib import Path

TARGET = (
    Path(__file__).resolve().parents[1]
    / "215_kamiooya"
    / "C1_cursor"
    / "1c_神・大家さん倶楽部_AI推進"
    / "神・大家さん倶楽部情報Q&Aチャットボット"
    / "scripts"
    / "supabase_healthcheck.py"
)

if not TARGET.is_file():
    raise SystemExit(f"healthcheck 本体がありません: {TARGET}")

runpy.run_path(str(TARGET), run_name="__main__")
