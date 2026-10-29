import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from notta_weekly_replace import match_video_id, plan


def src(key, provider=None):
    return {"id": 1, "source_key": key, "title": "t", "meta_json": {"transcript_provider": provider} if provider else {}}


class NottaWeeklyReplaceTests(unittest.TestCase):
    def test_video_id_from_filename_or_mapping(self):
        self.assertEqual(match_video_id("STEP2-1_803690477.xlsx", {}), "803690477")
        self.assertIsNone(match_video_id("2-1.xlsx", {}))
        self.assertEqual(match_video_id("2-1.xlsx", {"2-1.xlsx": {"vimeo_id": "803690477"}}), "803690477")
        self.assertIsNone(match_video_id("706381706_803690477.xlsx", {}))  # 2つあると決めない

    def test_whisper_is_replaced_but_vimeo_subtitles_are_held(self):
        w = src("westudy:a:vimeo:1", "local_whisper")
        self.assertEqual(plan([w], None), ("replace", [w]))
        self.assertEqual(plan([src("westudy:a:vimeo:1", "vimeo_auto")], None)[0], "hold")
        self.assertEqual(plan([w, src("notta:westudy:a:vimeo:1")], None)[0], "skip")

    def test_new_video_needs_slug_and_title(self):
        self.assertEqual(plan([], None)[0], "hold")
        self.assertEqual(plan([], {"slug": "step9", "title": "STEP9"})[0], "new")


if __name__ == "__main__":
    unittest.main()
