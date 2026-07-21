#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""build_delta_csv: 分類・板タイトル列が差分に残ること。"""

from __future__ import annotations

import csv
import json
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
BUILD = SCRIPTS / "build_delta_csv.py"
PY = sys.executable


def test_delta_keeps_category_columns() -> None:
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        full = td_path / "full.csv"
        state = td_path / "state.json"
        delta = td_path / "delta.csv"

        fieldnames = [
            "コメントID",
            "投稿日時",
            "投稿者名",
            "投稿者メール",
            "コメント内容",
            "親コメントID",
            "IP アドレス",
            "ユーザーエージェント",
            "ソース",
            "ソース系統",
            "ソース種別",
            "分類",
            "板タイトル",
        ]
        with full.open("w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fieldnames, lineterminator="\n")
            w.writeheader()
            w.writerow(
                {
                    "コメントID": "100",
                    "投稿日時": "2026-01-01 00:00:00",
                    "投稿者名": "A",
                    "投稿者メール": "",
                    "コメント内容": "known",
                    "親コメントID": "",
                    "IP アドレス": "",
                    "ユーザーエージェント": "",
                    "ソース": "WeStudy",
                    "ソース系統": "WeStudy",
                    "ソース種別": "コミュニティ情報",
                    "分類": "成果報告",
                    "板タイトル": "成果報告【実践】",
                }
            )
            w.writerow(
                {
                    "コメントID": "26972",
                    "投稿日時": "2026-07-16 00:00:00",
                    "投稿者名": "B",
                    "投稿者メール": "",
                    "コメント内容": "new",
                    "親コメントID": "",
                    "IP アドレス": "",
                    "ユーザーエージェント": "",
                    "ソース": "WeStudy",
                    "ソース系統": "WeStudy",
                    "ソース種別": "コミュニティ情報",
                    "分類": "成果報告",
                    "板タイトル": "成果報告【実践】",
                }
            )

        state.write_text(
            json.dumps({"version": 1, "comment_ids": ["100"]}, ensure_ascii=False),
            encoding="utf-8",
        )

        proc = subprocess.run(
            [
                PY,
                str(BUILD),
                "--full",
                str(full),
                "--state",
                str(state),
                "--delta",
                str(delta),
            ],
            cwd=str(SCRIPTS),
            capture_output=True,
            text=True,
            check=False,
        )
        assert proc.returncode == 0, proc.stderr or proc.stdout

        with delta.open("r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            assert reader.fieldnames is not None
            assert "分類" in reader.fieldnames
            assert "板タイトル" in reader.fieldnames
            rows = list(reader)

        assert len(rows) == 1
        assert rows[0]["コメントID"] == "26972"
        assert rows[0]["分類"] == "成果報告"
        assert rows[0]["板タイトル"] == "成果報告【実践】"


if __name__ == "__main__":
    test_delta_keeps_category_columns()
    print("OK")
