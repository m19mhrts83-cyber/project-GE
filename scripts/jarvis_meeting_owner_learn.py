"""Learning loop for 714 owner judgments: outcomes in, owner-reviewable proposals out.

Reads how the owner decided inferred-owner candidates (created / dismissed), keeps per-meeting
tallies and an accuracy figure, and writes *proposals* to a private state file. It never edits
the owner config and never turns anything into a standing rule: a proposal takes effect only when
the owner agrees and jarvis_meeting_owner.add_meeting_mapping is called for that meeting.
Read-only against sync_meta; no Slack/Todoist/Notion access.
"""
from __future__ import annotations
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Callable

sys.path.insert(0, str(Path(__file__).resolve().parent))
import jarvis_meeting_todo as todo  # noqa: E402

LEARNING = todo.REPO / '.jarvis_state' / 'meeting_owner_learning.json'
DECIDED = {'created': 'adopted', 'dismissed': 'dismissed'}


def summarize(outcomes: list[dict]) -> dict:
    """outcomes: [{meeting_id, label, status}] for inferred-owner candidates only."""
    tally: dict[tuple, dict] = defaultdict(lambda: {'adopted': 0, 'dismissed': 0, 'open': 0})
    for o in outcomes:
        t = tally[(o['meeting_id'], o['label'])]
        t[DECIDED.get(o['status'], 'open')] += 1
    proposals = []
    for (meeting_id, label), t in sorted(tally.items()):
        if t['adopted'] and not t['dismissed']:
            kind, ask = 'promote', '起票された。本人対応として確認済みにしてよいか'
        elif t['dismissed'] and not t['adopted']:
            kind, ask = 'review_demote', '見送られた。本人でなかったのか、不要な作業だっただけか（後者なら対応は維持）'
        elif t['adopted'] and t['dismissed']:
            kind, ask = 'review_mixed', '起票と見送りが混在。どの発言が本人かを確認'
        else:
            kind, ask = 'waiting', '本人の判断待ち'
        proposals.append({'meeting_id': meeting_id, 'label': label, 'kind': kind, 'ask': ask, **t, 'status': 'proposed'})
    adopted = sum(t['adopted'] for t in tally.values())
    dismissed = sum(t['dismissed'] for t in tally.values())
    decided = adopted + dismissed
    return {'adopted': adopted, 'dismissed': dismissed, 'decided': decided,
            'adopt_rate': round(adopted / decided, 3) if decided else None, 'proposals': proposals}


def collect(outbox: dict, fetch: Callable[[str], Any]) -> list[dict]:
    """Current cloud status of inferred-owner candidates; an unreadable row counts as open, never decided."""
    out = []
    for cid, c in outbox.items():
        res = c.get('owner_resolution') or {}
        if res.get('basis') != 'content_inference' and c.get('owner_inference') is None:
            continue
        try:
            raw = fetch(cid)
            status = json.loads(raw)['status'] if raw else 'open'
        except Exception:
            status = 'open'
        out.append({'meeting_id': c['meeting_id'], 'label': c.get('assignee', ''), 'status': status})
    return out


def run(outbox_path: Path = None, store=None, out_path: Path = LEARNING) -> dict:
    outbox = todo.load_json(outbox_path or todo.OUTBOX)
    store = store or todo.Store()
    result = summarize(collect(outbox, store.get))
    # Re-runs refresh tallies but keep the owner's earlier answers to each proposal.
    prior = {(p['meeting_id'], p['label']): p for p in (todo.load_json(out_path, {}).get('proposals', []) if Path(out_path).exists() else [])}
    for p in result['proposals']:
        old = prior.get((p['meeting_id'], p['label']))
        if old and old.get('status') in {'accepted', 'declined'} and old.get('kind') == p['kind']:
            p['status'] = old['status']
    todo.atomic_json(out_path, result)
    return {k: v for k, v in result.items() if k != 'proposals'} | {'proposals': len(result['proposals'])}


if __name__ == '__main__':
    print(json.dumps(run(), ensure_ascii=False))
