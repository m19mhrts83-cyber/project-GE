import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import jarvis_force_monthly as fm  # noqa: E402

TODAY = datetime(2026, 11, 28, tzinfo=ZoneInfo("Asia/Tokyo"))


def row(d, shop, yen, method="payment", cat="x", setting="常に集計に含める", income=0):
    return {"日付": d, "方法": method, "カテゴリ": cat, "お店": shop, "メモ": "", "支出": str(yen),
            "収入": str(income), "集計の設定": setting}


def test_classify_and_annual():
    rows = [
        row("2026-11-08", "ANTHROPIC* CLAUDE SU", 100),
        row("2026-11-24", "Apple iTunes Store", 3000),
        row("2026-07-26", "Apple iTunes Store", 2500),  # ChatGPT ではない
        row("2026-11-22", "TODOIST", 1200),  # 年額扱い（テスト用に閾値超えの値）
        row("2026-10-21", "TODOIST", 10),
        row("2026-07-07", "CURSOR", 7, setting="集計に含めない"),
    ]
    old = fm.ANNUAL_MIN["todoist"]
    fm.ANNUAL_MIN["todoist"] = 1000
    try:
        rep = fm.aggregate(rows, TODAY)
    finally:
        fm.ANNUAL_MIN["todoist"] = old
    assert rep["amounts"]["2026-11"] == {"claude": 100, "chatgpt": 3000, "todoist": 100}
    assert rep["amounts"]["2026-10"] == {"todoist": 10}
    assert "2026-07" in rep["amounts"] and rep["amounts"]["2026-07"] == {}
    assert rep["months"][0] == "2026-01" and rep["months"][-1] == "2026-11"
