#!/usr/bin/env python3
"""過去添付の棚卸し・再開可能な取込。既定は棚卸しのみ。原本は変更しない。"""
from __future__ import annotations

import argparse
import collections
import concurrent.futures
import fcntl
import hashlib
import json
import multiprocessing
import os
import signal
import threading
import time
import zipfile
from datetime import datetime, timezone
from urllib.parse import urlsplit
from pathlib import Path

import requests
from jarvis_kamiooya_attachments import ARCHIVE, Store, build_attachment, canonical_url, normalize_comment_id


def inspect_candidate(row, root):
    def deadline(signum, frame):
        raise TimeoutError('archive_read_timeout')
    old_handler = signal.signal(signal.SIGALRM, deadline)
    signal.setitimer(signal.ITIMER_REAL, 2)
    try:
        # 旧harvestは外部ページのhrefまで保存している。ファイル拡張子のない
        # fileリンクは原本候補と分離し、HTMLとして会員へ配らない。
        if row.get('kind') == 'file' and not Path(urlsplit(row['url']).path).suffix:
            return {'issue': 'page_link_without_file_extension'}
        meta, _ = build_attachment(row, root)
        return {'record': {'meta': meta, 'archive_path': str(Path(row['local_path']).resolve().relative_to(root.resolve()))}}
    except (ValueError, OSError, zipfile.BadZipFile) as exc:
        reason = str(exc) if isinstance(exc, ValueError) else type(exc).__name__
        if reason == 'unsupported_or_invalid_file':
            try:
                with Path(row.get('local_path', '')).open('rb') as f:
                    head = f.read(1024).lstrip().lower()
                if head.startswith((b'<!doctype html', b'<html')):
                    reason = 'html_page'
            except OSError:
                reason = 'missing_file'
        return {'issue': reason}
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, old_handler)


def inventory(catalogs, root=ARCHIVE, checkpoint=None):
    counts = collections.Counter()
    groups = {}
    issues = []
    for catalog in sorted(catalogs, key=lambda p: (p.stat().st_mtime_ns, str(p))):
        if not catalog.resolve().is_relative_to(root.resolve()):
            raise ValueError("catalog_outside_archive")
        ref = hashlib.sha256(str(catalog.relative_to(root)).encode()).hexdigest()[:16]
        # JSONLの区切りはLFのみ。splitlinesは本文内のU+2028等も分割する。
        for line_no, line in enumerate(catalog.read_text(encoding="utf-8").split('\n'), 1):
            if not line.strip():
                counts['blank_lines'] += 1
                continue
            try:
                row = json.loads(line)
                cid = normalize_comment_id(row.get('comment_id', ''))
                url = canonical_url(row.get('url', ''))
            except (ValueError, AttributeError):
                counts['invalid_catalog_rows'] += 1
                issues.append({'catalog_ref': ref, 'line': line_no, 'result': 'invalid_catalog_row'})
                continue
            counts['catalog_rows'] += 1
            ident = hashlib.sha256(f'{cid}\0{url}'.encode()).hexdigest()
            if ident in groups:
                counts['duplicate_rows'] += 1
            # 最新台帳・後の行を優先。同じURLでも更新された実体を取り込む。
            groups[ident] = row
    records = []
    cache = {}
    if checkpoint and checkpoint.exists():
        for line in checkpoint.read_text().splitlines():
            try:
                item = json.loads(line); cache[item['id']] = item
            except ValueError:
                pass
    checked = 0
    def consume(ident, row, stamp, result):
        nonlocal checked
        checked += 1
        if 'record' in result:
            records.append(result['record']); counts['eligible'] += 1
            counts['bytes'] += result['record']['meta']['byte_size']
            if checkpoint and cache.get(ident, {}).get('stamp') != stamp:
                with checkpoint.open('a') as out:
                    out.write(json.dumps({'id': ident, 'stamp': stamp, **result}) + '\n'); out.flush()
        else:
            counts[result['issue']] += 1
            issues.append({'id': ident, 'comment_id': normalize_comment_id(row['comment_id']), 'result': result['issue']})
        if checked % 100 == 0:
            print(json.dumps({'inventory_checked': checked, 'unique': len(groups)}), flush=True)
    # Driveのオンデマンド読込を1ファイルで全停止させない。子プロセス内で
    # 読込期限を設定し、成功したhashだけをcheckpointに残す。
    with concurrent.futures.ProcessPoolExecutor(max_workers=4, mp_context=multiprocessing.get_context('spawn')) as pool:
        futures = {}
        for ident, row in groups.items():
            source = Path(row.get('local_path', ''))
            try:
                stat = source.stat()
                stamp = hashlib.sha256(json.dumps([str(source), stat.st_mtime_ns, stat.st_size, row.get('name')]).encode()).hexdigest()
            except OSError:
                stamp = ''
            cached = cache.get(ident, {})
            if cached.get('stamp') == stamp and cached.get('record'):
                consume(ident, row, stamp, {'record': cached['record']})
            else:
                futures[pool.submit(inspect_candidate, row, root)] = (ident, row, stamp)
        for future in concurrent.futures.as_completed(futures):
            ident, row, stamp = futures[future]
            consume(ident, row, stamp, future.result())
    return {'version': 1, 'counts': dict(counts), 'unique': len(groups), 'records': records, 'issues': issues}


def rows_for_ids(store, table, ids, select, id_field='id'):
    result = {}
    for offset in range(0, len(ids), 100):
        rows = store.request('GET', '/rest/v1/' + table, params={'select': select, id_field: 'in.(' + ','.join(ids[offset:offset+100]) + ')', 'limit': 100}).json()
        result.update({str(row[id_field]): row for row in rows})
    return result


def apply_plan(plan, state, workers=3, max_files=100):
    store = Store()
    records = plan['records']
    ids = [r['meta']['id'] for r in records]
    comments = rows_for_ids(store, 'comments', sorted({r['meta']['comment_id'] for r in records}), 'comment_id', 'comment_id')
    old = rows_for_ids(store, 'community_attachments', ids, 'id,sha256,storage_path')
    done = {}
    if state.exists():
        for line in state.read_text().splitlines():
            try:
                r = json.loads(line)
                if r.get('result') in ('saved', 'unchanged'):
                    done[r['id']] = r['sha256']
            except ValueError:
                pass  # 強制終了で末尾行が欠けても既存成功分を維持する。
    pending, missing = [], []
    resumed = 0
    for row in records:
        meta = row['meta']
        if meta['comment_id'] not in comments:
            missing.append({'id': meta['id'], 'comment_id': meta['comment_id'], 'result': 'missing_comment'})
        elif done.get(meta['id']) == meta['sha256'] and old.get(meta['id'], {}).get('sha256') == meta['sha256'] and old[meta['id']]['storage_path'] == meta['storage_path']:
            resumed += 1
        else:
            pending.append(row)
    selected = pending[:max_files]
    store.ensure_bucket()
    local = threading.local()

    def worker(row):
        meta = row['meta']
        for attempt in range(3):
            try:
                if not hasattr(local, 'store'):
                    local.store = Store()
                source_root = state.parent / 'recovered' if row.get('recovery_file') else ARCHIVE
                path = (source_root / (row.get('recovery_file') or row['archive_path'])).resolve()
                if not path.is_relative_to(source_root.resolve()):
                    raise ValueError('file_outside_archive')
                data = path.read_bytes()
                if hashlib.sha256(data).hexdigest() != meta['sha256']:
                    raise ValueError('source_changed_rebuild_inventory')
                status = local.store.save(meta, data, old_record=old.get(meta['id']), publish=False)
                return {'id': meta['id'], 'sha256': meta['sha256'], 'result': status}
            except (ValueError, RuntimeError, requests.RequestException, OSError) as exc:
                if attempt < 2 and isinstance(exc, (requests.RequestException, RuntimeError)):
                    time.sleep(attempt + 1)
                    continue
                # エラーメッセージ/レスポンスは秘密やURLを含む可能性があるため記録しない。
                return {'id': meta['id'], 'sha256': meta['sha256'], 'result': 'failed', 'error_type': type(exc).__name__}
    counts = collections.Counter()
    failures = []
    by_id = {r['meta']['id']: r['meta'] for r in selected}
    # append-only/fsync。次の実行は成功済みhashと本番メタの双方で再開判定する。
    with state.open('a', encoding='utf-8') as out, concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        ready = []
        def flush():
            successful = [r for r in ready if r['result'] != 'failed']
            if successful:
                for attempt in range(3):
                    try:
                        store.request('POST', '/rest/v1/community_attachments', params={'on_conflict': 'id'}, json=[{**by_id[r['id']], 'updated_at': datetime.now(timezone.utc).isoformat()} for r in successful], headers={'Prefer': 'resolution=merge-duplicates,return=minimal'})
                        break
                    except (RuntimeError, requests.RequestException):
                        if attempt == 2:
                            for r in successful:
                                r.update(result='failed', error_type='metadata_publish_failed')
                        else:
                            time.sleep(attempt + 1)
            # メタの一括commitが成功してから成功checkpointを残す。
            for result in ready:
                counts[result['result']] += 1
                if result['result'] == 'failed':
                    failures.append(result)
                out.write(json.dumps(result) + '\n')
            out.flush(); os.fsync(out.fileno()); ready.clear()
            print(json.dumps({'processed': sum(counts.values()), 'selected': len(selected), **counts}), flush=True)
        for result in pool.map(worker, selected):
            ready.append(result)
            if len(ready) == 25:
                flush()
        if ready:
            flush()
    current = rows_for_ids(store, 'community_attachments', ids, 'id,sha256,storage_path')
    matching = sum(current.get(r['meta']['id'], {}).get('sha256') == r['meta']['sha256'] and current[r['meta']['id']]['storage_path'] == r['meta']['storage_path'] for r in records)
    return {'eligible': len(records), 'resumed': resumed, 'selected': len(selected), 'remaining': max(0, len(pending)-len(selected)), 'missing_comment': len(missing), 'metadata_matching': matching, 'counts': dict(counts), 'issues': missing + failures}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--catalog-list', type=Path, required=True)
    p.add_argument('--plan', type=Path, required=True)
    p.add_argument('--report', type=Path, required=True)
    p.add_argument('--state', type=Path)
    p.add_argument('--apply', action='store_true')
    p.add_argument('--reuse-plan', action='store_true')
    p.add_argument('--workers', type=int, choices=range(1, 5), default=3)
    p.add_argument('--max-files', type=int, default=100)
    args = p.parse_args()
    if args.max_files < 1 or args.max_files > 10000 or (args.apply and not args.state):
        p.error('apply requires state; max-files must be 1..10000')
    args.plan.parent.mkdir(parents=True, exist_ok=True)
    with args.plan.with_suffix('.lock').open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if args.reuse_plan:
            plan = json.loads(args.plan.read_text())
        else:
            checkpoint = args.plan.with_suffix('.inventory.jsonl')
            checkpoint.touch(mode=0o600, exist_ok=True)
            plan = inventory([Path(x) for x in args.catalog_list.read_text().splitlines() if x], checkpoint=checkpoint)
            args.plan.write_text(json.dumps(plan, ensure_ascii=False, indent=2)); args.plan.chmod(0o600)
        report = {'inventory': {k: v for k, v in plan.items() if k != 'records'}, 'apply': args.apply}
        if args.apply:
            args.state.parent.mkdir(parents=True, exist_ok=True)
            args.state.touch(mode=0o600, exist_ok=True)
            with args.state.with_suffix('.lock').open('w') as state_lock:
                fcntl.flock(state_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                report['execution'] = apply_plan(plan, args.state, args.workers, args.max_files)
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2)); args.report.chmod(0o600)
        print(json.dumps({k: v for k, v in report.items() if k != 'inventory'} | {'inventory_counts': plan['counts']}), flush=True)
        return 1 if report.get('execution', {}).get('counts', {}).get('failed') else 0


if __name__ == '__main__':
    raise SystemExit(main())
