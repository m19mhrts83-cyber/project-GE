import csv, hashlib, io, json, sys, tempfile, unittest
from pathlib import Path
from unittest.mock import Mock, patch
from PIL import Image
sys.path.insert(0,str(Path(__file__).parents[1]))
import jarvis_kamiooya_community_daily as mod

class CommunityDailyTest(unittest.TestCase):
    def row(self,url='https://westudy.co.jp/wp-content/uploads/a-1x1.png',cid='12'):
        return hashlib.sha256(f'{cid}\0{url}'.encode()).hexdigest(),{'url':url,'comment_id':cid,'kind':'image'}
    def store(self,ids=()):
        s=Mock();s.request.side_effect=lambda method,path,**kw:Mock(json=lambda: [{'id':x} for x in ids] if method=='GET' else 1000)
        s.exists_comment.return_value=True;s.save.return_value='saved';return s
    def png(self):
        b=io.BytesIO();Image.new('RGB',(4,5)).save(b,format='PNG');return b.getvalue()
    def test_attachment_only_addition_and_idempotent_next_run(self):
        ident,row=self.row();data=self.png();store=self.store()
        with patch.object(mod,'download',return_value=data) as fetch:
            result=mod.sync({ident:row},store,True,source=Mock())
        self.assertEqual(result,{'saved':1});self.assertEqual(fetch.call_count,1)
        meta,body=store.save.call_args.args
        self.assertEqual(body,data);self.assertEqual(meta['id'],ident);self.assertEqual((meta['image_width'],meta['image_height']),(4,5));self.assertIn('original_source_url',meta)
        with patch.object(mod,'download') as fetch:
            self.assertEqual(mod.sync({ident:row},self.store([ident]),True),{'existing':1});fetch.assert_not_called()
    def test_external_redirect_target_and_query_are_never_requested(self):
        for url in ['https://evil.test/file.pdf','https://westudy.co.jp:8443/wp-content/uploads/a.jpg','https://westudy.co.jp/wp-content/uploads/a.jpg?secret=x','https://westudy.co.jp/wp-content/uploads/%2e%2e/a.jpg','http://westudy.co.jp/wp-content/uploads/a.jpg']:
            ident,row=self.row(url)
            with patch.object(mod,'download') as fetch:
                self.assertEqual(mod.sync({ident:row},self.store(),True),{'untrusted_source':1});fetch.assert_not_called()
    def test_missing_parent_and_capacity_hold_are_visible(self):
        ident,row=self.row();s=self.store();s.exists_comment.return_value=False
        with patch.object(mod,'download') as fetch:
            self.assertEqual(mod.sync({ident:row},s,True),{'parent_pending':1});fetch.assert_not_called()
        s=self.store();s.request.side_effect=lambda method,path,**kw:Mock(json=lambda: [] if method=='GET' else 80_000_000_000)
        with patch.object(mod,'download',return_value=self.png()):self.assertEqual(mod.sync({ident:row},s,True),{'budget_held':1})
        s.save.assert_not_called()
    def test_missing_original_falls_back_to_validated_thumbnail(self):
        ident,row=self.row();s=self.store();data=self.png()
        with patch.object(mod,'download',side_effect=[None,data]):self.assertEqual(mod.sync({ident:row},s,True),{'saved':1})
        self.assertNotIn('original_source_url',s.save.call_args.args[0])
    def test_limit_is_not_silent_and_invalid_html_is_not_uploaded(self):
        rows=dict([self.row(cid='12'),self.row(cid='13')]);s=self.store()
        with patch.object(mod,'download',return_value=self.png()):
            result=mod.sync(rows,s,True,max_files=1)
        self.assertEqual(result,{'saved':1,'deferred':1})
        ident,row=self.row('https://westudy.co.jp/wp-content/uploads/file.pdf');row['kind']='file';s=self.store()
        with patch.object(mod,'download',return_value=b'<html>login</html>'):self.assertEqual(mod.sync({ident:row},s,True),{'failed':1})
        s.save.assert_not_called()
    def test_full_harvest_not_text_delta_is_input(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);p=root/'topic.csv';_,row=self.row()
            with p.open('w') as f:
                w=csv.DictWriter(f,fieldnames=['comment_id','body','attachments_json']);w.writeheader();w.writerow({'comment_id':'12','body':'unchanged','attachments_json':json.dumps([row])})
            self.assertEqual(len(mod.candidates(root)),1)
            (root/'empty.csv').write_text('irrelevant\n')
            self.assertEqual(len(mod.candidates(root)),1)
