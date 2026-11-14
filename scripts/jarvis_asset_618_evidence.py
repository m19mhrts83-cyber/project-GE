#!/usr/bin/env python3
"""618 fresh-capture receipts and verified private latest proof publishing.

Default preview; --apply performs the already-authorized publishing operation only.
No login, OTP, Slack, signed URLs, image deletion, or bucket creation here.
"""
from __future__ import annotations
import argparse
from datetime import date, datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import re
import sys
import uuid
from zoneinfo import ZoneInfo
from typing import Any
from jarvis_asset_618_runtime import Blocked, Busy, Run, ident, timestamp, atomic_json

BUCKET = 'asset-evidence'
MAX_BYTES = 10 * 1024 * 1024
REVIEWERS = {'owner', 'jarvis', 'codex', 'misslemon'}


def uuid_text(value: Any) -> str:
    try:
        if str(uuid.UUID(value)) != value:
            raise ValueError()
        return value
    except (ValueError, TypeError, AttributeError):
        raise Blocked('invalid_evidence_run_id') from None


def png_bytes(path: Path) -> bytes:
    from PIL import Image
    try:
        if path.is_symlink() or not path.is_file() or not 0 < path.stat().st_size <= MAX_BYTES:
            raise ValueError()
        raw = path.read_bytes()
        with Image.open(io.BytesIO(raw)) as im:
            if im.format != 'PNG' or getattr(im, 'n_frames', 1) != 1 or im.width < 100 or im.height < 50 or im.width * im.height > 20_000_000:
                raise ValueError()
            im.verify()
        return raw
    except Exception:
        raise Blocked('invalid_or_oversized_png') from None


def capture_receipt(path: Path, *, run_id: str, step: str, started_at: str,
                    finished_at: str, fresh_screen: bool) -> dict[str, Any]:
    """Only the capture wrapper issues these; a review of identity/date is still required."""
    raw = png_bytes(path)
    start, finish = timestamp(started_at), timestamp(finished_at)
    modified = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc)
    if not start <= modified <= finish or (finish-start).total_seconds() > 7200:
        raise Blocked('old_or_unrelated_capture')
    return {'path': str(path.resolve()), 'sha256': hashlib.sha256(raw).hexdigest(),
            'capture_run_id': uuid_text(run_id), 'step': ident(step),
            'captured_at': modified.isoformat(), 'started_at': started_at, 'finished_at': finished_at,
            'candidate_type': 'fresh_screen' if fresh_screen else 'derived_reference'}


def reviewed_artifact(receipt: dict, item: dict) -> tuple[bytes, dict]:
    if receipt.get('candidate_type') != 'fresh_screen':
        raise Blocked('reference_is_not_screen_proof')
    validation = item.get('validation')
    if not isinstance(validation, dict) or any(validation.get(k) is not True for k in ('normal_page','account_match','contract_match','source_date_match')) or item.get('reviewed_by') not in REVIEWERS:
        raise Blocked('identity_and_date_review_required')
    start, captured, finish = (timestamp(receipt.get(k)) for k in ('started_at','captured_at','finished_at'))
    if not start <= captured <= finish or (finish-start).total_seconds() > 7200 or finish > datetime.now(timezone.utc):
        raise Blocked('invalid_capture_window')
    uuid_text(receipt.get('capture_run_id'))
    path = Path(receipt.get('path') or '')
    raw = png_bytes(path)
    if hashlib.sha256(raw).hexdigest() != receipt.get('sha256'):
        raise Blocked('capture_hash_mismatch')
    modified = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc)
    if abs((modified-captured).total_seconds()) > .001:
        raise Blocked('capture_modified_after_receipt')
    try:
        source_date = date.fromisoformat(item.get('source_as_of'))
        if source_date.isoformat() != item['source_as_of'] or source_date > captured.astimezone(ZoneInfo('Asia/Tokyo')).date():
            raise ValueError()
    except (ValueError, TypeError):
        raise Blocked('invalid_source_date') from None
    return raw, {'sha256': receipt['sha256'], 'captured_at': receipt['captured_at'],
                 'source_as_of': source_date.isoformat(), 'capture_run_id': receipt['capture_run_id'],
                 'verified_by': item['reviewed_by']}


def coordinates(item: dict) -> dict:
    if not isinstance(item, dict) or item.get('account_scope') not in ('portfolio','liquidity'):
        raise Blocked('invalid_evidence_scope')
    return {'account_scope': item['account_scope'], **{k: ident(item.get(k)) for k in ('account_id','contract_key','view_key')}}


def slot_path(owner_id: str, coords: dict, slot: str) -> str:
    if slot not in ('a','b'):
        raise Blocked('invalid_storage_slot')
    return f"618/latest/{uuid_text(owner_id)}/{coords['account_scope']}/{coords['account_id']}/{coords['contract_key']}/{coords['view_key']}.{slot}.png"


def rpc_row(client: Any, name: str, args: dict) -> dict:
    result = client.rpc(name, args).execute().data
    row = result[0] if isinstance(result, list) and len(result) == 1 else result
    if not isinstance(row, dict) or not row.get('id'):
        raise Blocked('evidence_metadata_response_invalid')
    return row


class EvidenceStore:
    def __init__(self, client: Any, owner_id: str):
        self.client, self.owner_id = client, uuid_text(owner_id)
        self.checked = False

    def check_owner(self):
        try:
            rows = self.client.table('asset_evidence_owners').select('user_id').eq('user_id',self.owner_id).execute().data
            bucket = self.client.storage.get_bucket(BUCKET)
            public = bucket.get('public') if isinstance(bucket,dict) else getattr(bucket,'public',None)
            if not rows or len(rows) != 1 or public is not False:
                raise ValueError()
            self.checked = True
        except Exception:
            raise Blocked('evidence_owner_not_enrolled_or_unavailable') from None

    def publish(self, item: dict, receipt: dict, run_id: str) -> dict:
        if not self.checked:
            self.check_owner()
        coords = coordinates(item)
        attempt = str(uuid.uuid4())
        current = None
        try:
            current = rpc_row(self.client,'asset_evidence_begin',{'p_owner':self.owner_id,
                'p_scope':coords['account_scope'],'p_account':coords['account_id'],
                'p_contract':coords['contract_key'],'p_view':coords['view_key'],'p_attempt':attempt})
            raw, meta = reviewed_artifact(receipt,item)
            if current.get('captured_at') and (timestamp(meta['captured_at']) <= timestamp(current['captured_at']) or meta['source_as_of'] < current['source_as_of']):
                raise Blocked('older_proof_rejected')
            slot = 'b' if current.get('active_slot') == 'a' else 'a'
            path = slot_path(self.owner_id,coords,slot)
            bucket = self.client.storage.from_(BUCKET)
            bucket.upload(path,raw,{'content-type':'image/png','cache-control':'0','upsert':'true'})
            if hashlib.sha256(bucket.download(path)).hexdigest() != meta['sha256']:
                raise Blocked('storage_readback_mismatch')
            committed = rpc_row(self.client,'asset_evidence_commit',{
                'p_id':current['id'],'p_attempt':attempt,'p_sha':meta['sha256'],
                'p_captured':meta['captured_at'],'p_asof':meta['source_as_of'],
                'p_capture_run':meta['capture_run_id'],'p_run':uuid_text(run_id),'p_reviewer':meta['verified_by']})
            # Read the persisted pointer independently; an RPC response is not enough.
            rows = self.client.table('asset_evidence_latest').select('*').eq('id',current['id']).eq('owner_id',self.owner_id).limit(1).execute().data
            if not rows or any(rows[0].get(k) != value for k,value in {'storage_path':path,'sha256':meta['sha256'],'run_id':run_id,'last_attempt_status':'ok'}.items()):
                raise Blocked('evidence_metadata_readback_unverified')
            return {'status':'ok','evidence_id':committed['id']}
        except Exception as exc:
            if current:
                try:
                    self.client.rpc('asset_evidence_fail',{'p_id':current['id'],'p_attempt':attempt}).execute()
                except Exception:
                    pass  # Pending remains visible; never replace or remove the old good proof.
            return {'status':'error','code':str(exc) if isinstance(exc,Blocked) else 'evidence_update_failed_or_pending'}


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--manifest',type=Path,required=True)
    ap.add_argument('--owner-id',required=True)
    ap.add_argument('--apply',action='store_true')
    ap.add_argument('--recover',action='store_true')
    ap.add_argument('--owner-confirmed',action='store_true')
    args=ap.parse_args()
    try:
        owner=uuid_text(args.owner_id)
        data=json.loads(args.manifest.read_text(encoding='utf-8'))
        if args.recover:
            if not args.apply or not args.owner_confirmed:
                raise Blocked('recovery_requires_confirmed_operator_request')
            from jarvis_portfolio_weekly import load_private_env, sb_client
            from jarvis_asset_618_runtime import SharedLock
            load_private_env();client=sb_client();store=EvidenceStore(client,owner);store.check_owner()
            with SharedLock():
                rid,aid=uuid_text(data['evidence_id']),uuid_text(data['attempt_id'])
                rows=client.table('asset_evidence_latest').select('id').eq('id',rid).eq('owner_id',owner).execute().data
                if len(rows or []) != 1: raise Blocked('evidence_not_owned')
                client.rpc('asset_evidence_recover',{'p_id':rid,'p_attempt':aid}).execute()
                state=client.table('asset_evidence_latest').select('last_attempt_id,last_attempt_status,last_attempt_code').eq('id',rid).eq('owner_id',owner).execute().data
                if not state or state[0].get('last_attempt_id') != aid or state[0].get('last_attempt_status') != 'failed' or state[0].get('last_attempt_code') != 'operator_recovered':
                    raise Blocked('recovery_not_confirmed')
            print(json.dumps({'recovery_requested':True}));return 0
        receipts=json.loads(Path(data['capture_receipts']).read_text(encoding='utf-8'))['artifacts']
        items=data['items']
        if not isinstance(items,list) or not items:
            raise Blocked('evidence_items_required')
        selected=[]
        seen=set()
        for item in items:
            coords=coordinates(item);key=tuple(coords.values())
            if key in seen: raise Blocked('duplicate_evidence_target')
            seen.add(key)
            index=item['artifact_index']
            if type(index) is not int or not 0 <= index < len(receipts): raise Blocked('invalid_artifact_index')
            selected.append((item,receipts[index]))
        if not args.apply:
            for item,receipt in selected: reviewed_artifact(receipt,item)
            print(json.dumps({'preview':True,'reviewed_items':len(selected),'writes':0}));return 0
        from jarvis_portfolio_weekly import load_private_env,sb_client
        load_private_env();client=sb_client();store=EvidenceStore(client,owner);store.check_owner()
        with Run('evidence_publish',[item['account_id'] for item,_ in selected],client) as run:
            results=[]
            for item,receipt in selected:
                if item['account_id'] not in run.allowed: continue
                result=store.publish(item,receipt,run.data['run_id']);results.append(result)
                status='error' if run.data['results'].get(item['account_id'])=='error' else result['status']
                run.record({item['account_id']:{'status':status}})
            run.data['image_results']=results;run.persist()
            print(json.dumps({'run_id':run.data['run_id'],'updated':sum(r['status']=='ok' for r in results),
                              'failed':sum(r['status']=='error' for r in results),
                              'held':len(run.data['decision_context']['held_targets'])}))
            return 0 if results and all(r['status']=='ok' for r in results) and not run.data['decision_context']['held_targets'] else 2
    except (Blocked,Busy,ValueError,OSError,KeyError,TypeError,IndexError) as exc:
        print('# asset618: '+(str(exc) if isinstance(exc,(Blocked,Busy)) else 'invalid_evidence_input'),file=sys.stderr)
        return 2


if __name__=='__main__':raise SystemExit(main())
