"""講座動画の毎日新着取込（2026-11-11）: 平日は新着のあるコースだけ、lesson 差分は追加だけ。"""

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

REPO = Path(__file__).resolve().parents[2]
QA_SCRIPTS = REPO / "215_kamiooya/C1_cursor/1c_神・大家さん倶楽部_AI推進/神・大家さん倶楽部情報Q&Aチャットボット/scripts"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


delta = _load("build_lesson_delta_csv", QA_SCRIPTS / "build_lesson_delta_csv.py")


def row(cid: str, h: str) -> dict:
    return {"コメントID": cid, "コンテンツハッシュ": h, "コメント内容": "本文"}


class LessonDeltaAddOnlyTest(unittest.TestCase):
    def test_add_only_keeps_existing_state_and_skips_delete(self):
        state = {"lesson_desc_a": "h1", "lesson_desc_b": "h2"}
        rows, new_state = delta.build_delta([row("lesson_desc_c", "h3")], state, add_only=True)
        self.assertEqual([r["コメントID"] for r in rows], ["lesson_desc_c"])
        self.assertEqual(rows[0]["差分種別"], "add")
        self.assertEqual(new_state, {"lesson_desc_a": "h1", "lesson_desc_b": "h2", "lesson_desc_c": "h3"})

    def test_add_only_ignores_known_rows(self):
        rows, new_state = delta.build_delta([row("lesson_desc_a", "changed")], {"lesson_desc_a": "h1"}, add_only=True)
        self.assertEqual(rows, [])
        self.assertEqual(new_state, {"lesson_desc_a": "h1"})

    def test_full_mode_still_detects_delete(self):
        rows, _ = delta.build_delta([row("lesson_desc_c", "h3")], {"lesson_desc_a": "h1"})
        self.assertEqual(sorted(r["差分種別"] for r in rows), ["add", "delete"])


class VideoDailyModeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, str(REPO / "scripts"))
        try:
            cls.vw = _load("kamiooya_video_weekly", REPO / "scripts/kamiooya_video_weekly.py")
        except Exception as e:  # Mac 専用の依存が無い環境では飛ばす
            raise unittest.SkipTest(f"kamiooya_video_weekly を読めない: {e}")

    def test_resolve_mode(self):
        jst = ZoneInfo("Asia/Tokyo")
        self.assertEqual(self.vw.resolve_mode("auto", datetime(2026, 11, 15, 12, tzinfo=jst)), "weekly")  # 日曜
        self.assertEqual(self.vw.resolve_mode("auto", datetime(2026, 11, 11, 12, tzinfo=jst)), "daily")  # 水曜
        self.assertEqual(self.vw.resolve_mode("weekly", datetime(2026, 11, 11, 12, tzinfo=jst)), "weekly")

    def test_pending_lessons_only_video_lessons(self):
        with tempfile.TemporaryDirectory() as d:
            m = Path(d) / "course2_status.json"
            m.write_text(json.dumps({"lessons": [
                {"slug": "a", "status": "no_video"},
                {"slug": "b", "status": "vtt_ready", "title": "新しい講義"},
                {"slug": "c", "status": "no_subtitles"},
                {"slug": "d", "status": "error"},
            ]}), encoding="utf-8")
            self.assertEqual([L["slug"] for L in self.vw.pending_lessons(m)], ["b", "c"])
            self.assertEqual(self.vw.pending_lessons(Path(d) / "missing.json"), [])

    def test_daily_message(self):
        msg = self.vw.build_message("11/12", {"videos": 1, "chunks": 20, "whisper_videos": 0}, {}, [], None,
                                    Path("動画取込_20261112.md"), mode="daily", new_titles=["新しい講義"])
        self.assertIn("動画の新着取込", msg)
        self.assertIn("新しい講義", msg)
        self.assertNotIn("Notta", msg)


if __name__ == "__main__":
    unittest.main()
