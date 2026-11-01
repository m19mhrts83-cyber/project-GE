import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).parents[1]))
import jarvis_kamiooya_attachment_batch as batch
import jarvis_kamiooya_attachments as attachments


class BatchTests(unittest.TestCase):
    def test_latest_catalog_wins_and_html_is_counted(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); photo = root/'a.jpg'; photo.write_bytes(b'\xff\xd8\xffdata')
            page = root/'link'; page.write_bytes(b'<!doctype html><html>not an attachment</html>')
            row = {'comment_id':'123', 'url':'https://westudy.co.jp/a.jpg?token=x', 'local_path':str(photo), 'name':'original.jpg'}
            cat = root/'attachments.jsonl'; cat.write_text(json.dumps(row)+'\n'+json.dumps({**row,'name':'new.jpg'})+'\n'+json.dumps({**row,'comment_id':'124','url':'https://example.com/page','local_path':str(page)})+'\n{broken\n')
            p = batch.inventory([cat], root)
            self.assertEqual(p['counts']['eligible'],1)
            self.assertEqual(p['counts']['duplicate_rows'],1)
            self.assertEqual(p['counts']['html_page'],1)
            self.assertEqual(p['counts']['invalid_catalog_rows'],1)
            self.assertEqual(p['records'][0]['meta']['original_name'],'new.jpg')
            self.assertNotIn('token=',json.dumps(p))

    def test_does_not_hide_missing_latest_snapshot(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);cat=root/'attachments.jsonl'
            cat.write_text(json.dumps({'comment_id':'123','url':'https://westudy.co.jp/a.pdf','local_path':str(root/'missing.pdf')}))
            p=batch.inventory([cat],root)
            self.assertEqual(len(p['records']),0)
            self.assertEqual(len(p['issues']),1)

    def test_unicode_line_separator_inside_json_is_not_a_record_boundary(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);photo=root/'a.jpg';photo.write_bytes(b'\xff\xd8\xffdata')
            row={'comment_id':'123','url':'https://westudy.co.jp/a.jpg','local_path':str(photo),'body_excerpt':'before\u2028after'}
            cat=root/'attachments.jsonl';cat.write_text(json.dumps(row,ensure_ascii=False)+'\n')
            p=batch.inventory([cat],root)
            self.assertEqual(p['counts']['catalog_rows'],1)
            self.assertEqual(p['counts'].get('invalid_catalog_rows',0),0)

    def test_resume_requires_database_hash_and_missing_comment_is_visible(self):
        meta={'id':'a','comment_id':'1','sha256':'hash','storage_path':'comments/1/a.pdf'}
        plan={'records':[{'meta':meta}, {'meta':{**meta,'id':'b','comment_id':'2'}}]}
        store=Mock()
        with tempfile.TemporaryDirectory() as d:
            state=Path(d)/'state.jsonl';state.write_text(json.dumps({'id':'a','sha256':'hash','result':'saved'})+'\n')
            with patch.object(batch,'Store',return_value=store), patch.object(batch,'rows_for_ids',side_effect=[{'1':{}},{'a':meta},{'a':meta}]):
                result=batch.apply_plan(plan,state)
            self.assertEqual(result['resumed'],1)
            self.assertEqual(result['missing_comment'],1)
            self.assertEqual(result['metadata_matching'],1)

    def test_office_and_html_disguised_as_csv(self):
        import zipfile
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            for ext,inner in [('docx','word/document.xml'),('pptx','ppt/presentation.xml')]:
                p=root/('file.'+ext)
                with zipfile.ZipFile(p,'w') as z:
                    z.writestr('[Content_Types].xml','x');z.writestr(inner,'x')
                self.assertEqual(attachments.inspect_file(p,root)[2],'.'+ext)
            p=root/'fake.csv';p.write_text('<html>bad,not a csv</html>')
            with self.assertRaises(ValueError):attachments.inspect_file(p,root)

    def test_size_ceiling_rejects_before_read(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);p=root/'huge.pdf'
            with p.open('wb') as f:f.truncate(attachments.MAX_BYTES+1)
            with self.assertRaisesRegex(ValueError,'file_size_limit'):attachments.inspect_file(p,root)

    def test_prefetched_metadata_still_verifies_uploaded_body_before_linking(self):
        import hashlib
        data=b'file';store=object.__new__(attachments.Store)
        meta={'id':'a','sha256':hashlib.sha256(data).hexdigest(),'storage_path':'comments/1/a.pdf','content_type':'application/pdf'}
        store.existing=Mock(side_effect=AssertionError('already fetched'))
        store.request=Mock(side_effect=[Mock(),Mock(content=data),Mock()])
        self.assertEqual(store.save(meta,data,old_record=None),'saved')
        self.assertEqual([c.args[0] for c in store.request.call_args_list],['POST','GET','POST'])

    def test_batch_upload_does_not_expose_metadata_before_batch_commit(self):
        import hashlib
        data=b'file';store=object.__new__(attachments.Store)
        meta={'id':'a','sha256':hashlib.sha256(data).hexdigest(),'storage_path':'comments/1/a.pdf','content_type':'application/pdf'}
        store.request=Mock(side_effect=[Mock(),Mock(content=data)])
        self.assertEqual(store.save(meta,data,old_record=None,publish=False),'saved')
        self.assertEqual(len(store.request.call_args_list),2)

    def test_legacy_http_is_only_a_stable_source_identifier(self):
        self.assertEqual(attachments.canonical_url('http://example.com/a.pdf?token=x'), 'http://example.com/a.pdf')
        with self.assertRaises(ValueError):attachments.canonical_url('file:///tmp/a.pdf')

    def test_failed_metadata_commit_never_records_upload_as_success(self):
        import hashlib
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);file=root/'a.pdf';file.write_bytes(b'%PDF-file')
            meta={'id':'a','comment_id':'1','sha256':hashlib.sha256(file.read_bytes()).hexdigest(),'storage_path':'comments/1/a.pdf'}
            plan={'records':[{'meta':meta,'archive_path':'a.pdf'}]};store=Mock();store.save.return_value='saved';store.request.side_effect=RuntimeError('supabase_http_503')
            state=root/'state.jsonl'
            with patch.object(batch,'ARCHIVE',root),patch.object(batch,'Store',return_value=store),patch.object(batch,'rows_for_ids',side_effect=[{'1':{}},{},{}]),patch.object(batch.time,'sleep'):
                result=batch.apply_plan(plan,state)
            self.assertEqual(result['counts'],{'failed':1})
            self.assertEqual(json.loads(state.read_text())['result'],'failed')


if __name__=='__main__':unittest.main()
