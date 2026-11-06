import copy,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parents[1]))
from jarvis_qa_comment_pages import add_page_route
class CommentPagesTest(unittest.TestCase):
 def test_existing_routes_and_guard_are_unchanged(self):
  source={'api':[{'name':'read','endpoint':'POST /internal/read/comments','steps':[{'check':{'condition':'input.__gateway_secret == fixture'}}],'output':{}}]};before=copy.deepcopy(source)
  result=add_page_route(source);self.assertEqual(source,before);self.assertEqual(result['api'][:-1],source['api']);page=result['api'][-1];self.assertEqual(page['steps'][0],source['api'][0]['steps'][0]);query=page['steps'][-1]['tableFetchMany'];self.assertEqual(query['limit'],500);self.assertEqual(query['orderBy'],'id ASC');self.assertEqual(query['whereRaw']['params'],['input.after_id']);self.assertIn('admin_%',query['whereRaw']['sql'])
 def test_unguarded_or_duplicate_alias_is_rejected(self):
  with self.assertRaises(ValueError):add_page_route({'api':[{'endpoint':'POST /internal/read/comments','steps':[]}]})
