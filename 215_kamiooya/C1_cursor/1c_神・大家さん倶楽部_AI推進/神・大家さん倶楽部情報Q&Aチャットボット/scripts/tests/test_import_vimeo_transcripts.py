import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from import_vimeo_transcripts import build_records, parse_videos, sync_raimo, sync_supabase


class VimeoImportTests(unittest.TestCase):
    def test_multiple_video_clocks_and_description_are_separate(self):
        text = '''## レッスン説明文
[00:01] 説明文を字幕として使わない
## 動画 1: Vimeo 123 — 日本語
[00:01] 一つ目
[01:02:03] 長時間の動画
## 動画 2: Vimeo 456 — 日本語
[00:00] 二つ目
## 動画 3: Vimeo 789 — 字幕なし
_字幕取得不可_
'''
        videos = parse_videos(text)
        self.assertEqual([v[0] for v in videos], ['123', '456'])
        self.assertEqual(videos[0][1][1].start_sec, 3723)
        self.assertEqual(videos[1][1][0].start_sec, 0)
        records = build_records({'slug': 'test', 'title': 'テスト', 'url': 'https://westudy.co.jp/lesson/test'}, text, 'origin.md', '応用')
        self.assertEqual(len(records), 2)
        self.assertTrue(records[0][0]['meta_json']['provisional'])
        self.assertNotEqual(records[0][1][0]['chunk_key'], records[1][1][0]['chunk_key'])
        self.assertEqual(records, build_records({'slug': 'test', 'title': 'テスト', 'url': 'https://westudy.co.jp/lesson/test'}, text, 'origin.md', '応用'))

    def test_no_subtitles_produce_no_transcript(self):
        self.assertEqual(parse_videos('## レッスン説明文\n本文だけ'), [])

    def test_canonical_source_is_not_overwritten(self):
        class Query:
            def select(self, *args): return self
            def eq(self, *args): return self
            def execute(self): return SimpleNamespace(data=[{'id': 9, 'meta_json': {'provisional': False}}])
        client = SimpleNamespace(table=lambda name: Query())
        self.assertEqual(sync_supabase(client, {'source_key':'canonical'}, [], True), 0)

    def test_raimo_retry_adds_only_missing_chunks(self):
        source = {'source_key':'westudy:test:vimeo:123', 'meta_json': {'provisional':True,'content_sha256':'hash'}}
        chunks = [{ 'chunk_key':key, 'start_sec':0, 'end_sec':None, 'speaker':None,'content':'本文','search_text':'本文'} for key in ('old','new')]
        cache = {'sources':[source], 'keys':{'old'}}
        with patch('import_vimeo_transcripts.post_json', return_value=(200,'{}')) as send:
            self.assertEqual(sync_raimo('https://example.com', source, chunks, cache), 1)
            self.assertEqual(send.call_args.args[2]['chunk_key'], 'new')
            self.assertEqual(sync_raimo('https://example.com', source, chunks, cache), 0)
            self.assertEqual(send.call_count, 1)

    def test_changed_transcript_requires_explicit_replacement(self):
        source = {'source_key':'westudy:test:vimeo:123', 'meta_json': {'provisional':True,'content_sha256':'new'}}
        cache = {'sources':[{'source_key':source['source_key'], 'meta_json':{'provisional':True,'content_sha256':'old'}}], 'keys':set()}
        with patch('import_vimeo_transcripts.post_json') as send:
            with self.assertRaisesRegex(RuntimeError, '字幕変更'):
                sync_raimo('https://example.com', source, [], cache)
            send.assert_not_called()


if __name__ == '__main__':
    unittest.main()
