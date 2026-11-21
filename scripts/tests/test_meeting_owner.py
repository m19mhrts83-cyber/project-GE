"""Identity matching with synthetic names; no real data/network or private config."""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import jarvis_meeting_owner as owner
import jarvis_meeting_todo as todo


def policy(**extra):
    return owner.validate_policy({'version':1,'owner_aliases':['Owner A','OWNER-ALT'],
        'other_aliases':['Other B'],'meetings':{},**extra})

class IdentityTests(unittest.TestCase):
    def test_exact_normalized_aliases_only(self):
        p=policy()
        self.assertEqual(owner.resolve_assignee('a','  ＯＷＮＥＲ　Ａ ',p)['identity'],'owner')
        self.assertEqual(owner.resolve_assignee('a','Owner A extra',p)['identity'],'held')
        self.assertEqual(owner.resolve_assignee('a','Owner',p)['identity'],'held')
        self.assertEqual(owner.resolve_assignee('a','Other B',p)['identity'],'other')
    def test_first_person_role_speaker_never_global_owner(self):
        p=policy()
        for label,reason in [('私','first_person_unmapped'),('自分','first_person_unmapped'),('課長','role_mapping_missing'),('Speaker 1','speaker_mapping_missing')]:
            self.assertEqual(owner.resolve_assignee('a',label,p)['reason'],reason)
            with self.assertRaises(ValueError):policy(owner_aliases=[label])
    def test_confirmed_mapping_is_scoped_to_one_meeting(self):
        p=policy(meetings={'meeting-a':{label:{'identity':'owner','confirmed':True,'evidence':'explicit owner confirmation'} for label in ['Speaker 1','私','課長']}})
        for label in ['Speaker 1','私','課長']:
            self.assertEqual(owner.resolve_assignee('meeting-a',label,p)['identity'],'owner')
            self.assertEqual(owner.resolve_assignee('meeting-b',label,p)['identity'],'held')
    def test_other_speaker_mapping_and_pending_alias(self):
        p=policy(pending_aliases=['Almost Owner'],meetings={'a':{'Speaker 2':{'identity':'other','confirmed':True,'evidence':'confirmed different person'}}})
        self.assertEqual(owner.resolve_assignee('a','Speaker 2',p)['identity'],'other')
        self.assertEqual(owner.resolve_assignee('a','Almost Owner',p)['identity'],'held')
    def test_missing_multiple_and_unknown_names_stay_held(self):
        p=policy()
        for label,reason in [('', 'missing_assignee'),('Owner A / Other B','multiple_assignees'),('Owner A、Other B','multiple_assignees'),('Unlisted Name','unconfirmed_name')]:
            self.assertEqual(owner.resolve_assignee('a',label,p)['reason'],reason)
    def test_invalid_or_contradictory_config_stops(self):
        for extra in [{'other_aliases':['Owner A']},{'meetings':{'a':{'Speaker 1':{'identity':'owner','confirmed':False,'evidence':'x'}}}}, {'meetings':{'a':{'Speaker 1':{'identity':'owner','confirmed':True}}}}, {'meetings':{'a':{'Owner A':{'identity':'other','confirmed':True,'evidence':'x'}}}}]:
            with self.assertRaises(ValueError):policy(**extra)
    def test_missing_or_broken_config_does_not_restore_public_regex(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'missing.json'
            self.assertEqual(owner.resolve_assignee('a','Owner A',owner.load_owner_policy(path))['reason'],'policy_not_configured')
            path.write_text('{broken')
            with self.assertRaises(ValueError):owner.load_owner_policy(path)
    def test_candidate_records_identity_reason_and_excludes_confirmed_other(self):
        with patch.object(todo,'load_owner_policy',return_value=policy()):
            a=todo.candidate('m',{'assignee':'Owner A','todo':'Task','evidence':'source'})
            b=todo.candidate('m',{'assignee':'OWNER-ALT','todo':'Task','evidence':'source'})
            other=todo.candidate('m',{'assignee':'Other B','todo':'Other task','evidence':'source'})
            self.assertEqual(a['candidate_id'],b['candidate_id'])
            self.assertTrue(a['owner_confirmed']);self.assertEqual(other['status'],'excluded')
            self.assertEqual(len(a['owner_resolution']['policy_fingerprint']),64)
    def test_other_candidates_never_dispatch(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(todo,'load_owner_policy',return_value=policy()):
            c=todo.candidate('m',{'assignee':'Other B','todo':'Task','evidence':'source'})
            path=Path(tmp)/'outbox';todo.atomic_json(path,{c['candidate_id']:c})
            with patch.object(todo,'Store',side_effect=AssertionError('network')):
                self.assertEqual(todo.dispatch(path=path)['posted'],0)

class RecheckTests(unittest.TestCase):
    def test_revoked_or_missing_policy_blocks_queued_old_owner(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'outbox'
            with patch.object(todo,'load_owner_policy',return_value=policy()):
                c=todo.candidate('m',{'assignee':'Owner A','todo':'Task','evidence':'source'})
            todo.atomic_json(path,{c['candidate_id']:c})
            missing={'version':1,'configured':False,'owner_aliases':[],'other_aliases':[],'meetings':{}}
            with patch.object(todo,'load_owner_policy',return_value=missing),patch.object(todo,'Store',side_effect=AssertionError('cloud write')):
                self.assertEqual(todo.dispatch(path=path)['posted'],0)
            self.assertEqual(todo.load_json(path)[c['candidate_id']]['status'],'held')
    def test_speaker_notation_is_not_a_global_identity(self):
        p=policy(meetings={'a':{'Speaker 1':{'identity':'owner','confirmed':True,'evidence':'explicit confirmation'}}})
        for label in ['Speaker1','speaker_01','話者 1']:
            self.assertEqual(owner.resolve_assignee('a',label,p)['identity'],'owner')
            self.assertEqual(owner.resolve_assignee('b',label,p)['identity'],'held')
