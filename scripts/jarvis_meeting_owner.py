"""Identity matching from private, explicitly confirmed aliases; never infer a speaker."""
from __future__ import annotations
import hashlib
import json
import os
import re
import unicodedata
from pathlib import Path
from typing import Any

DEFAULT_CONFIG = Path(__file__).resolve().parents[1] / 'config' / 'meeting_owner.private.json'
FIRST_PERSON = {'私','わたし','わたくし','自分','僕','俺','当方','i','me','myself'}
ROLES = {'担当者','課長','部長','先生','講師','司会','主催者','保護者','当社','弊社','自社'}
SPEAKER = re.compile(r'^(?:speaker|話者|発言者)[ _-]*(\d+)$',re.I)
MULTIPLE = re.compile(r'[,、/;&＆・]|\s+(?:and|と|及び)\s+',re.I)


def normalized(value: str) -> str:
    text=re.sub(r'\s+',' ',unicodedata.normalize('NFKC',value)).strip().casefold()
    speaker=SPEAKER.fullmatch(text)
    return f'speaker {int(speaker[1])}' if speaker else text


def validate_policy(raw: Any) -> dict:
    if not isinstance(raw,dict) or raw.get('version')!=1:
        raise ValueError('invalid owner policy version')
    result={'version':1}
    for key in ('owner_aliases','other_aliases'):
        values=raw.get(key,[])
        if not isinstance(values,list) or any(not isinstance(v,str) or not v.strip() for v in values):
            raise ValueError('aliases must be nonempty strings')
        result[key]=sorted(set(normalized(v) for v in values))
        if any(v in FIRST_PERSON or v in ROLES or SPEAKER.fullmatch(v) for v in result[key]):
            raise ValueError('generic roles/pronouns/speaker IDs require a per-meeting mapping')
    if set(result['owner_aliases']) & set(result['other_aliases']):
        raise ValueError('conflicting owner/other aliases')
    meetings=raw.get('meetings',{})
    if not isinstance(meetings,dict):raise ValueError('meetings must be an object')
    result['meetings']={}
    for mid,mapping in meetings.items():
        if not isinstance(mid,str) or not mid or not isinstance(mapping,dict):
            raise ValueError('invalid meeting mapping')
        converted={}
        for alias,decision in mapping.items():
            if not isinstance(alias,str) or not alias.strip() or not isinstance(decision,dict):
                raise ValueError('invalid assignee mapping')
            if decision.get('identity') not in {'owner','other'} or decision.get('confirmed') is not True or not isinstance(decision.get('evidence'),str) or not decision['evidence'].strip():
                raise ValueError('meeting mappings require confirmed identity and evidence')
            key=normalized(alias)
            if key in converted:raise ValueError('duplicate normalized mapping')
            # A meeting override must not contradict a confirmed global identity.
            if (key in result['owner_aliases'] and decision['identity']!='owner') or (key in result['other_aliases'] and decision['identity']!='other'):
                raise ValueError('meeting mapping conflicts with global identity')
            converted[key]={'identity':decision['identity'],'evidence':decision['evidence'],'confirmed':True}
        result['meetings'][mid]=converted
    # Pending suggestions are audit data only; never read by the resolver.
    result['configured']=True
    return result


def load_owner_policy(path: Path | None = None) -> dict:
    path=path or Path(os.getenv('JARVIS_MEETING_OWNER_CONFIG') or DEFAULT_CONFIG)
    if not path.is_file():
        return {'version':1,'owner_aliases':[],'other_aliases':[],'meetings':{},'configured':False}
    return validate_policy(json.loads(path.read_text(encoding='utf-8')))


def resolve_assignee(meeting_id: str, assignee: str, policy: dict) -> dict:
    value=normalized(assignee)
    fingerprint=hashlib.sha256(json.dumps(policy,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
    def answer(identity,reason):
        return {'identity':identity,'reason':reason,'policy_version':1,'policy_fingerprint':fingerprint}
    if not value:return answer('held','missing_assignee')
    if not policy.get('configured',True):return answer('held','policy_not_configured')
    if value in policy.get('owner_aliases',[]):return answer('owner','confirmed_owner_alias')
    if value in policy.get('other_aliases',[]):return answer('other','confirmed_other_alias')
    if MULTIPLE.search(value):return answer('held','multiple_assignees')
    mapping=policy.get('meetings',{}).get(meeting_id,{}).get(value)
    if mapping and mapping.get('confirmed') is True:
        return answer(mapping['identity'],'confirmed_meeting_mapping')
    if value in FIRST_PERSON:return answer('held','first_person_unmapped')
    if SPEAKER.fullmatch(value):return answer('held','speaker_mapping_missing')
    if value in ROLES:return answer('held','role_mapping_missing')
    return answer('held','unconfirmed_name')
