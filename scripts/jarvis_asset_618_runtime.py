"""618 common process lock, run provenance and owner-decision adapter.

No financial operations and no Slack sends. Live decisions use the existing owner_decisions.
"""
from __future__ import annotations

from contextvars import ContextVar
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
import uuid
from typing import Any

from jarvis_owner_decision_log import contract_row

SURFACE = 'asset_618'
ROOT = Path.home() / 'Library/Logs/jarvis_portfolio'
CURRENT: ContextVar[Any] = ContextVar('asset618_run', default=None)
EFFECTS = {'exclude_target', 'include_target', 'retry_target', 'review_note', 'hold_target'}
ACTIONS = {'rule_accept', 'rule_once', 'rule_reject', 'rule_revert', 'comment'}


class Busy(RuntimeError):
    pass


class Blocked(RuntimeError):
    pass


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def ident(value: Any) -> str:
    if not isinstance(value, str) or not re.fullmatch(r'[a-zA-Z0-9_-]{1,100}', value):
        raise Blocked('invalid_target_or_key')
    return value


def timestamp(value: Any) -> datetime:
    if not isinstance(value, str):
        raise Blocked('invalid_decision_date')
    try:
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None:
            raise ValueError()
        return parsed.astimezone(timezone.utc)
    except ValueError:
        raise Blocked('invalid_decision_date') from None


class SharedLock:
    """One kernel lock across worktrees and CLI/worker/launchd entry points.

    Kernel releases on process exit; never evict a live owner based on lock age.
    Existing legacy mkdir locks fail closed until the old process has released them.
    """
    def __init__(self, root: Path = ROOT):
        self.root, self.fd = root, None

    def __enter__(self):
        self.root.mkdir(parents=True, exist_ok=True)
        if (self.root / 'weekly.lock.d').exists():
            raise Busy('legacy_collection_running')
        self.fd = os.open(self.root / 'asset618.execution.lock', os.O_CREAT | os.O_RDWR, 0o600)
        try:
            fcntl.flock(self.fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            os.close(self.fd)
            self.fd = None
            raise Busy('asset618_busy') from None
        return self

    def __exit__(self, *_):
        if self.fd is not None:
            fcntl.flock(self.fd, fcntl.LOCK_UN)
            os.close(self.fd)
            self.fd = None


def atomic_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent,
                                     prefix='.asset618-', delete=False) as fp:
        json.dump(value, fp, ensure_ascii=False, indent=2)
        fp.write('\n')
        name = fp.name
    os.replace(name, path)


class DecisionStore:
    def __init__(self, client: Any):
        self.client = client

    def read(self) -> list[dict[str, Any]]:
        try:
            rows, offset = [], 0
            while True:
                data = (self.client.table('owner_decisions')
                        .select('id,surface,employee,action,target_id,payload')
                        .eq('employee', '618').eq('surface', SURFACE)
                        .order('id').range(offset, offset + 499).execute().data)
                if not isinstance(data, list):
                    raise ValueError()
                rows.extend(data)
                if len(data) < 500:
                    return rows
                offset += 500
        except Exception:
            raise Blocked('decision_read_failed') from None

    def save(self, row: dict[str, Any]) -> int:
        """Explicit caller authorization only. Failed writes never activate a rule."""
        key = row['payload']['idem_key']
        try:
            existing = (self.client.table('owner_decisions').select('id,payload')
                        .eq('payload->>idem_key', key).limit(1).execute().data)
            if not existing:
                try:
                    existing = self.client.table('owner_decisions').insert(row).execute().data
                except Exception:
                    # Concurrent delivery may have hit the existing unique idem_key index.
                    existing = (self.client.table('owner_decisions').select('id,payload')
                                .eq('payload->>idem_key', key).limit(1).execute().data)
            if not existing or existing[0]['payload'].get('asset618_fingerprint') != row['payload']['asset618_fingerprint']:
                raise ValueError()
            return int(existing[0]['id'])
        except Exception:
            raise Blocked('decision_not_persisted_or_key_conflict') from None


def prepare_decision(data: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise Blocked('invalid_decision_input')
    action = data.get('action')
    if action not in ACTIONS or data.get('owner_confirmed') is not True:
        raise Blocked('explicit_owner_decision_required')
    if not isinstance(data.get('choice'), str) or not data['choice'].strip():
        raise Blocked('explicit_owner_choice_required')
    for field in ('reason', 'ai_proposal'):
        if data.get(field) is not None and not isinstance(data[field], str):
            raise Blocked('invalid_decision_text')
    spec = data.get('rule')
    if not isinstance(spec, dict):
        raise Blocked('decision_spec_required')
    spec = dict(spec)
    spec['decision_key'] = ident(spec.get('decision_key'))
    targets = spec.get('targets')
    if not isinstance(targets, list) or not targets:
        raise Blocked('explicit_targets_required')
    spec['targets'] = sorted({ident(x) for x in targets})
    from jarvis_asset_618_report import PORTFOLIO_IDS, OPERATIONS
    known = set(PORTFOLIO_IDS) | set(OPERATIONS) | {
        'sony_life_policy_loan', 'sony_life_chikage_policy_loan',
        'loan', 'paypay', 'sbi_net', 'axa', 'sbi_sec', 'bloomo', 'akatsuki', 'sony', 'prudential'}
    if not set(spec['targets']) <= known:
        raise Blocked('unknown_decision_target')
    if action in ('rule_accept', 'rule_once'):
        if spec.get('effect') not in EFFECTS:
            raise Blocked('unsupported_rule_effect')
        timestamp(spec.get('effective_from'))
        if spec.get('expires_at'):
            if timestamp(spec['expires_at']) <= timestamp(spec['effective_from']):
                raise Blocked('invalid_decision_window')
        if action == 'rule_once':
            spec['run_id'] = ident(spec.get('run_id'))
            spec['allow_retry'] = spec.get('allow_retry') is True
    if action == 'rule_revert' and (type(spec.get('reverts_id')) is not int or spec['reverts_id'] <= 0):
        raise Blocked('revert_id_required')
    spec['owner_confirmed'] = True
    key = 'asset618:' + ident(data.get('idem_key'))
    row = contract_row(surface=SURFACE, action=action, source='chat_or_voice', employee='618',
                       target_type='asset618_decision', target_id=spec['decision_key'],
                       ai_proposal=data.get('ai_proposal'), note=data.get('reason'),
                       payload={'asset_618': spec}, idem_key=key)
    row['final_text'] = str(data.get('choice') or '')[:8000] or None
    row['payload']['asset618_fingerprint'] = hashlib.sha256(
        json.dumps({k: v for k, v in row.items() if k not in ('created_at',)}, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    return row


def resolve_decisions(rows: list[dict[str, Any]], targets: list[str], run_id: str,
                      *, retry_of: str | None = None, now: datetime | None = None) -> dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    requested = set(targets)
    permanent, once, revoked = {}, {}, set()
    hold = set()
    seen_ids = set()
    related = []
    if not isinstance(rows, list) or any(not isinstance(r, dict) or type(r.get('id')) is not int for r in rows):
        raise Blocked('invalid_decision_history')
    for row in sorted(rows, key=lambda r: r['id']):
        if row.get('employee') != '618' or row.get('surface') != SURFACE:
            continue
        rid = row.get('id')
        if type(rid) is not int or rid <= 0 or rid in seen_ids:
            raise Blocked('invalid_decision_history')
        seen_ids.add(rid)
        payload = row.get('payload')
        if not isinstance(payload, dict):
            raise Blocked('invalid_decision_history')
        spec = payload.get('asset_618')
        if not isinstance(spec, dict):
            raise Blocked('invalid_decision_history')
        refs = spec.get('targets')
        if not isinstance(refs, list) or not refs or not all(isinstance(x, str) for x in refs):
            raise Blocked('invalid_decision_targets')
        affected = requested.intersection(refs)
        confirmed = spec.get('owner_confirmed') is True
        if row.get('action') == 'rule_revert':
            if confirmed and type(spec.get('reverts_id')) is int:
                revoked.add(spec['reverts_id'])
            elif affected:
                hold.update(affected)
            continue
        if affected:
            related.append(rid)
        action = row.get('action')
        if action not in ('rule_accept', 'rule_once'):
            continue
        if not confirmed:
            hold.update(affected)
            continue
        key = ident(spec.get('decision_key'))
        item = (row, spec, affected)
        if action == 'rule_accept':
            permanent[key] = item  # Latest adoption replaces earlier even if later revoked/expired.
        elif spec.get('run_id') == run_id or (retry_of and spec.get('run_id') == retry_of and spec.get('allow_retry') is True):
            try:
                if timestamp(spec.get('effective_from')) > now or (spec.get('expires_at') and timestamp(spec['expires_at']) <= now):
                    continue
            except Blocked:
                hold.update(affected)
                continue
            once[key] = item
    for row in rows:
        if row.get('employee') != '618' or row.get('surface') != SURFACE or row.get('action') != 'rule_revert':
            continue
        spec = row['payload']['asset_618']
        reference = next((r for r in rows if r.get('id') == spec.get('reverts_id')), None)
        if spec.get('owner_confirmed') is True and (not reference or reference.get('action') not in ('rule_accept', 'rule_once') or reference.get('surface') != SURFACE or reference.get('employee') != '618' or reference['payload']['asset_618'].get('decision_key') != spec.get('decision_key') or reference['id'] >= row['id']):
            raise Blocked('invalid_revert_reference')
    applied, effects = [], {}
    for key in permanent.keys() | once.keys():
        item = once.get(key) or permanent.get(key)
        row, spec, affected = item
        if row['id'] in revoked:
            # Cancelling a once-only override allows the standing rule to remain.
            standing = permanent.get(key) if key in once else None
            if not standing or standing[0]['id'] in revoked:
                continue
            row, spec, affected = standing
        try:
            start = timestamp(spec.get('effective_from'))
            end = timestamp(spec['expires_at']) if spec.get('expires_at') else None
            if end and end <= start:
                raise Blocked('invalid_decision_window')
            if start > now or (end and now >= end):
                continue
            effect = spec.get('effect')
            if effect not in EFFECTS:
                raise Blocked('unsupported_rule_effect')
        except Blocked:
            hold.update(affected)
            continue
        applied.append(row['id'])
        for target in affected:
            effects.setdefault(target, set()).add(effect)
    excluded = set()
    for target, effect in effects.items():
        if 'hold_target' in effect:
            hold.add(target)
        if {'include_target', 'exclude_target'} <= effect:
            hold.add(target)
        elif 'exclude_target' in effect:
            excluded.add(target)
    applied.sort()
    return {'applied_decision_ids': applied,
            'applied_rule_version': hashlib.sha256(json.dumps(applied).encode()).hexdigest()[:16],
            'excluded_targets': sorted(excluded - hold), 'held_targets': sorted(hold),
            'allowed_targets': sorted(requested - excluded - hold),
            'related_decision_ids': sorted(related)}


class Run:
    def __init__(self, kind: str, targets: list[str], client: Any = None, *, preview: bool = False,
                 retry_of: str | None = None, root: Path = ROOT, run_id: str | None = None):
        self.root = root
        self.lock = SharedLock(root)
        self.client = client
        self.preview = preview
        if run_id is not None:
            try:
                if str(uuid.UUID(run_id)) != run_id:
                    raise ValueError()
            except (ValueError, TypeError, AttributeError):
                raise Blocked('invalid_run_id') from None
        self.data = {'run_id': run_id or str(uuid.uuid4()), 'kind': kind,
                     'target_ids': sorted({ident(x) for x in targets}), 'retry_of': retry_of,
                     'started_at': now_iso(), 'status': 'running', 'results': {}}

    @property
    def path(self):
        return self.root / 'asset618-runs' / (self.data['run_id'] + '.json')

    def persist(self):
        atomic_json(self.path, self.data)

    def __enter__(self):
        self.lock.__enter__()
        if self.path.exists():
            self.lock.__exit__()
            raise Busy('run_id_already_used')
        try:
            rows = [] if self.preview else DecisionStore(self.client).read()
            self.data['decision_context'] = resolve_decisions(
                rows, self.data['target_ids'], self.data['run_id'], retry_of=self.data['retry_of'])
            for target in self.data['decision_context']['held_targets']:
                self.data['results'][target] = 'held'
            for target in self.data['decision_context']['excluded_targets']:
                self.data['results'][target] = 'excluded'
            self.persist()
            self.token = CURRENT.set(self)
            return self
        except BaseException:
            self.data['status'] = 'blocked'
            try:
                self.persist()
            finally:
                self.lock.__exit__()
            raise

    @property
    def allowed(self):
        return self.data['decision_context']['allowed_targets']

    def record(self, sources: dict[str, Any]):
        for target in self.allowed:
            if target not in sources:
                continue
            row = sources.get(target) or {}
            status = row.get('status') if isinstance(row, dict) else None
            note = str(row.get('note') or '').lower() if isinstance(row, dict) else ''
            if status == 'ok' and 'preserved' in note:
                status = 'error'
            elif status == 'ok' and any(x in note for x in ('reused', 'manual', 'cost-update')):
                status = 'reference'
            self.data['results'][target] = status if status in ('ok', 'error', 'reference', 'skipped') else 'unverified'
        self.persist()

    def __exit__(self, typ, exc, tb):
        self.data['finished_at'] = now_iso()
        if typ:
            self.data['status'] = 'failed'
        elif self.preview:
            self.data['status'] = 'preview'
        elif not self.data['results']:
            self.data['status'] = 'skipped'
        elif all(v in ('ok', 'excluded') for v in self.data['results'].values()):
            self.data['status'] = 'complete'
        else:
            self.data['status'] = 'partial'
        try:
            self.persist()
        finally:
            CURRENT.reset(self.token)
            self.lock.__exit__()


def current_metadata() -> dict[str, Any]:
    run = CURRENT.get()
    if not run:
        return {}
    plan = run.data['decision_context']
    return {'run_id': run.data['run_id'], 'started_at': run.data['started_at'], 'retry_of': run.data['retry_of'],
            'target_ids': run.data['target_ids'],
            'applied_decision_ids': plan['applied_decision_ids'],
            'applied_rule_version': plan['applied_rule_version'],
            'held_targets': plan['held_targets'],
            'excluded_targets': plan['excluded_targets'],
            'decision_read': 'not_read_preview' if run.preview else 'ok',
            'numeric_readbacks': run.data.get('numeric_readbacks', {})}


def retry_targets(run_id: str, kind: str, root: Path = ROOT) -> list[str]:
    try:
        if str(uuid.UUID(run_id)) != run_id:
            raise ValueError()
        row = json.loads((root / 'asset618-runs' / (run_id + '.json')).read_text())
        if row['run_id'] != run_id or row['kind'] != kind or row['status'] not in ('partial', 'failed'):
            raise ValueError()
        results = row['results']
        if not isinstance(results, dict):
            raise ValueError()
        # An interrupted run may have no per-target result yet.
        return [ident(x) for x in row['target_ids'] if results.get(x) not in ('ok', 'excluded')]
    except (OSError, ValueError, KeyError, TypeError):
        raise Blocked('invalid_or_nonretryable_run') from None


def target_allowed(target: str) -> bool:
    run = CURRENT.get()
    return run is None or target in run.allowed

def restricted() -> bool:
    run = CURRENT.get()
    return bool(run and run.data.get('restricted'))
