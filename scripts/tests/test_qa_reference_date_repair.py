import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parents[1]))
from jarvis_qa_reference_date_repair import source_date,plan
class DateRepairTest(unittest.TestCase):
 def test_timezone_is_explicit_without_inventing_a_date(self):
  self.assertEqual(source_date('2026-11-03 11:32:00'),'2026-11-03T11:32:00+09:00')
  self.assertEqual(source_date('2026-11-03T02:32:00Z'),'2026-11-03T02:32:00+00:00')
  for bad in ['',None,'unknown','2026-99-02','November sometime','2026年11月']:self.assertIsNone(source_date(bad))
 def test_only_exact_missing_dates_are_repaired_and_conflicts_are_held(self):
  source=[{'comment_id':'1','posted_at':'2026-11-03'},{'comment_id':'2','posted_at':'2026-11-03'},{'comment_id':'3','posted_at':'2026-11-03'},{'comment_id':'3','posted_at':'2025-11-03'},{'comment_id':'admin_a','posted_at':'2026-11-03'}]
  existing=[{'comment_id':'1','posted_at':None},{'comment_id':'2','posted_at':'2024-01-01'},{'comment_id':'3','posted_at':None},{'comment_id':'4','posted_at':None}]
  repairs,counts=plan(source,existing);self.assertEqual([r['comment_id'] for r in repairs],['1']);self.assertEqual(counts['conflicting_ids'],1)
