"""python3 -m unittest scripts/course_theme/test_openchat_ranking.py（Gemini・DB は呼ばない）"""
import datetime as dt
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import openchat_ranking as oc  # noqa: E402


def post(chat, d, u, text, r=0):
    return {"chat": chat, "d": d, "u": u, "text": text, "r": r}


class BuildTest(unittest.TestCase):
    def test_counts_are_made_by_script_across_chats(self):
        a, b = "33融資相談G【神大家】", "02初心者G【神大家】"
        local = [
            {"gid": "g1", "chat": a, "topic": "自己資金はいくら", "posts": [post(a, "2026-11-10", "u1", "自己資金は？", 5), post(a, "2026-08-01", "u2", "頭金は？")]},
            {"gid": "g2", "chat": b, "topic": "頭金の目安", "posts": [post(b, "2026-11-01", "u1", "頭金どれくらい？", 2)]},
            {"gid": "g3", "chat": b, "topic": "火災保険", "posts": [post(b, "2026-11-02", "u3", "火災保険は？")]},
        ]
        name = {"g1": "自己資金の目安", "g2": "自己資金の目安", "g3": "火災保険の選び方"}
        ranking, by_chat = oc.build(local, name, dt.date(2026, 11, 16))
        top = ranking[0]
        self.assertEqual(top["topic"], "自己資金の目安")
        self.assertEqual((top["count"], top["people"], top["replies"], top["recent"]), (3, 2, 7, 2))
        self.assertEqual(top["chats"], [{"chat": "33融資相談G", "n": 2}, {"chat": "02初心者G", "n": 1}])
        self.assertEqual(top["examples"][0]["text"], "自己資金は？")  # 返信の多い投稿が先
        self.assertEqual(by_chat[0]["chat"], "02初心者G")
        self.assertEqual(by_chat[0]["questions"], 2)
        self.assertNotIn("u1", str(ranking) + str(by_chat).replace("'u'", ""))

    def test_group_batch_keeps_missing_posts_and_drops_non_questions(self):
        qs = [post("c", "2026-11-01", "u1", "質問A？"), post("c", "2026-11-01", "u2", "ありがとうございます？"), post("c", "2026-11-01", "u3", "質問B？")]
        with mock.patch.object(oc, "gemini", return_value={"groups": [{"topic": "A", "ids": ["p1", "p9"]}, {"topic": "(質問以外)", "ids": ["p2"]}]}):
            out = oc.group_batch("c", qs)
        self.assertEqual([(t, len(ps)) for t, ps in out], [("A", 1), ("質問B？", 1)])

    def test_batches_split_by_chat(self):
        qs = [post("x", "d", "u", "t")] * (oc.BATCH + 1) + [post("y", "d", "u", "t")]
        self.assertEqual([(c, len(q)) for c, q in oc.batches(qs)], [("x", oc.BATCH), ("x", 1), ("y", 1)])


if __name__ == "__main__":
    unittest.main()
