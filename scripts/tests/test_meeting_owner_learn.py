"""Learning-loop tests with synthetic data; no network, no real names."""
import json
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import jarvis_meeting_owner_learn as learn
import jarvis_meeting_todo as todo


def row(mid, label, status):
    return {'meeting_id': mid, 'label': label, 'status': status}


class SummarizeTests(unittest.TestCase):
    def test_proposals_by_outcome_and_rate(self):
        r = learn.summarize([row('a', 'Speaker 1', 'created'), row('b', 'Speaker 2', 'dismissed'),
                             row('c', 'Speaker 1', 'created'), row('c', 'Speaker 1', 'dismissed'), row('d', 'Speaker 1', 'posted')])
        kinds = {p['meeting_id']: p['kind'] for p in r['proposals']}
        self.assertEqual(kinds, {'a': 'promote', 'b': 'review_demote', 'c': 'review_mixed', 'd': 'waiting'})
        self.assertEqual((r['adopted'], r['dismissed'], r['adopt_rate']), (2, 2, 0.5))
        self.assertTrue(all(p['status'] == 'proposed' for p in r['proposals']))

    def test_no_decisions_has_no_rate(self):
        self.assertIsNone(learn.summarize([])['adopt_rate'])
        self.assertIsNone(learn.summarize([row('a', 'Speaker 1', 'queued')])['adopt_rate'])


class CollectRunTests(unittest.TestCase):
    outbox = {'x': {'meeting_id': 'a', 'assignee': 'Speaker 1', 'owner_inference': {'identity': 'owner', 'evidence': 'e'}},
              'y': {'meeting_id': 'a', 'assignee': 'Owner A', 'owner_resolution': {'basis': 'owner_confirmed'}},
              'z': {'meeting_id': 'b', 'assignee': 'Speaker 2', 'owner_resolution': {'basis': 'content_inference'}}}

    def test_only_inferred_candidates_and_unreadable_rows_stay_open(self):
        def fetch(cid):
            if cid == 'z':
                raise OSError('down')
            return json.dumps({'status': 'created'})
        got = learn.collect(self.outbox, fetch)
        self.assertEqual([(g['meeting_id'], g['status']) for g in got], [('a', 'created'), ('b', 'open')])

    def test_run_writes_proposals_only_and_keeps_owner_answers(self):
        class Fake:
            def get(self, cid):
                return json.dumps({'status': 'created'})
        with tempfile.TemporaryDirectory() as tmp:
            ob, out = Path(tmp) / 'ob.json', Path(tmp) / 'learn.json'
            todo.atomic_json(ob, self.outbox)
            self.assertEqual(learn.run(ob, Fake(), out)['proposals'], 2)
            data = json.loads(out.read_text())
            data['proposals'][0]['status'] = 'accepted'
            out.write_text(json.dumps(data))
            learn.run(ob, Fake(), out)
            self.assertEqual(json.loads(out.read_text())['proposals'][0]['status'], 'accepted')


if __name__ == '__main__':
    unittest.main()
