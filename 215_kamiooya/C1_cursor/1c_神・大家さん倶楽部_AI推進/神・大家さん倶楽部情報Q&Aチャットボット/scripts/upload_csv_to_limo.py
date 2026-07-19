#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""後方互換: upload_csv_to_raimo.py へ委譲する。新規は Raimo 名を使うこと。"""
from __future__ import annotations

import runpy
from pathlib import Path

if __name__ == "__main__":
    target = Path(__file__).with_name("upload_csv_to_raimo.py")
    runpy.run_path(str(target), run_name="__main__")
