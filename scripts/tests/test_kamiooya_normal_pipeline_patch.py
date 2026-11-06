import copy,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from kamiooya_normal_pipeline_patch import patch,ENDPOINT
class NormalPipelinePatchTests(unittest.TestCase):
 def fixture(self):
  steps=[{'check':{'condition':'input.__gateway_secret == fixture-only'}},{'tableInsert':{'table':'chat_messages'},'as':'userMessage'},{'llm':{'model':'same-model','prompt':'same-keyword-prompt'},'as':'keyword'}]
  steps += [{'tableFetchMany':{'table':name,'limit':limit},'as':name} for name,limit in [('relatedCommunityComments',80),('relatedLessonComments',40),('relatedChunks',50)]]
  steps += [{'calculate':{'expression':"'same-full-evidence-prompt' + fetched.relatedCommunityComments"},'as':'promptText'},{'llm':{'model':'same-model','prompt':'computed.promptText'},'as':'answer'},{'llm':{'model':'same-model','prompt':'same-id-extraction'},'as':'usedSources'},{'tableInsert':{'table':'chat_messages'},'as':'assistantMessage'}]
  return {'api':[{'endpoint':'POST /chat-sessions/{id}/messages','steps':steps}]}
 def test_guard_search_and_original_routes_are_unchanged(self):
  before=self.fixture();saved=copy.deepcopy(before);after=patch(before);self.assertEqual(before,saved);self.assertEqual(after['api'][0],saved['api'][0]);route=after['api'][-1];self.assertEqual(route['endpoint'],ENDPOINT)
  self.assertEqual(route['steps'][0],saved['api'][0]['steps'][0]);self.assertEqual([s for s in route['steps'] if 'tableFetchMany' in s],[s for s in saved['api'][0]['steps'] if 'tableFetchMany' in s]);self.assertEqual(sum('llm' in s for s in route['steps']),2);self.assertFalse(any('tableInsert' in s for s in route['steps']));self.assertEqual(patch(after),after)
 def test_unexpected_source_layout_is_not_silently_rewritten(self):
  source=self.fixture();source['api'][0]['steps'].pop(0)
  with self.assertRaises(ValueError):patch(source)
