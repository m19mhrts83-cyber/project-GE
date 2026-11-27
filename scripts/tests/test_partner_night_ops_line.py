import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from jarvis_partner_night_pipeline import build_ops_line  # noqa: E402


def test_normal_night_is_silent():
    assert build_ops_line(line_n=3, export_n=0, fails=[], notes=[]) is None


def test_line_skip_is_red_with_reason():
    t = build_ops_line(
        line_n=0, export_n=0, fails=["Mac版LINE起動中（トークン保護でLINEスキップ）"], notes=[]
    )
    assert t.startswith("【111 ") and "🔴止まった" in t and "Mac版LINE起動中" in t
    assert "\n" not in t


def test_zero_without_fail_says_zero_ken_without_emoji():
    t = build_ops_line(line_n=0, export_n=0, fails=[], notes=["公式取込は2h以内に済みで省略"])
    assert "｜件:—｜" in t and "0件（" in t and "省略" in t


def test_partial_when_some_imported_but_failed():
    t = build_ops_line(line_n=0, export_n=2, fails=["line exit=1"], notes=[])
    assert "🟡途中" in t
