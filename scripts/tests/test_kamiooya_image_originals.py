import sys,io,hashlib,unittest
from pathlib import Path
from unittest.mock import Mock,patch
from PIL import Image
sys.path.insert(0,str(Path(__file__).parents[1]))
import jarvis_kamiooya_image_originals as mod
from jarvis_kamiooya_attachments import Store

class OriginalImagesTest(unittest.TestCase):
    def test_only_exact_trusted_upload_thumbnail_urls(self):
        self.assertEqual(mod.original_url('https://westudy.co.jp/wp-content/uploads/2026/11/a-150x150.jpg'),'https://westudy.co.jp/wp-content/uploads/2026/11/a.jpg')
        for url in ['https://evil.test/wp-content/uploads/a-150x150.jpg','https://westudy.co.jp:444/wp-content/uploads/a-150x150.jpg','https://westudy.co.jp/wp-content/uploads/a-150x150.jpg?token=x','https://westudy.co.jp/unrelated/a-150x150.jpg','http://westudy.co.jp/wp-content/uploads/a-150x150.jpg']:
            self.assertIsNone(mod.original_url(url))
    def test_recovered_bytes_and_identity_preserved_without_reencoding(self):
        b=io.BytesIO();Image.new('RGB',(4,5)).save(b,format='PNG');data=b.getvalue()
        row={'id':'a'*64,'comment_id':'12','bucket':'community-attachments','source_url':'https://westudy.co.jp/wp-content/uploads/a-1x1.png','byte_size':10}
        store=Mock();store.request.return_value.json.return_value=1000
        with patch.object(mod,'download',return_value=data):result=mod.recover(store,row,True)
        meta,saved=store.save.call_args.args
        self.assertEqual(result['result'],'saved');self.assertEqual(saved,data);self.assertEqual(meta['id'],row['id']);self.assertEqual(meta['source_url'],row['source_url']);self.assertEqual(meta['sha256'],hashlib.sha256(data).hexdigest());self.assertEqual((meta['image_width'],meta['image_height']),(4,5))
    def test_original_is_not_replaced_by_old_thumbnail_import(self):
        store=object.__new__(Store);data=b'original'
        old={'original_source_url':'https://westudy.co.jp/wp-content/uploads/a.jpg','storage_path':'comments/12/hash.jpg','sha256':hashlib.sha256(data).hexdigest()}
        store.existing=Mock(return_value=old);store.request=Mock(return_value=Mock(content=data))
        self.assertEqual(store.save({'id':'a','storage_path':'comments/12/thumb.jpg'},b'thumb'),'original_retained')
        self.assertEqual(store.request.call_count,1);self.assertEqual(store.request.call_args.args[0],'GET')
    def test_missing_original_and_unknown_budget_fail_closed(self):
        row={'id':'a','comment_id':'12','bucket':'community-attachments','source_url':'https://westudy.co.jp/wp-content/uploads/a-1x1.png','byte_size':10}
        store=Mock()
        with patch.object(mod,'download',return_value=None):self.assertEqual(mod.recover(store,row,True)['result'],'source_missing')
        b=io.BytesIO();Image.new('RGB',(4,5)).save(b,format='PNG');store.request.return_value.json.return_value=None
        with patch.object(mod,'download',return_value=b.getvalue()):self.assertEqual(mod.recover(store,row,True)['result'],'budget_held')
        store.save.assert_not_called()
    def test_weekly_collector_uses_the_same_original_url_rule(self):
        import ast,re
        source=Path(__file__).parents[2]/'ProgramCode/alfred_python/westudy_forum_all.py'
        tree=ast.parse(source.read_text());fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='original_upload_url');scope={'re':re}
        exec(compile(ast.Module(body=[fn],type_ignores=[]),str(source),'exec'),scope)
        url='https://westudy.co.jp/wp-content/uploads/2026/11/a-150x150.jpg'
        self.assertEqual(scope['original_upload_url'](url),mod.original_url(url))
    def test_mpo_camera_jpeg_keeps_its_original_bytes(self):
        image=Mock();image.format='MPO';image.width=400;image.height=300;image.size=(400,300);image.__enter__=Mock(return_value=image);image.__exit__=Mock(return_value=False)
        with patch.object(mod.Image,'open',return_value=image):
            size,kind=mod.image_info(b'jpeg-camera-original')
        self.assertEqual(size,(400,300));self.assertEqual(kind,('image/jpeg','.jpg'))
