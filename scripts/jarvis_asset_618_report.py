#!/usr/bin/env python3
"""618 Phase 1: read existing results and create sanitized Slack drafts. Never sends."""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import date, datetime, timedelta
import hashlib
import json
import re
import logging
import os
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

JST = ZoneInfo('Asia/Tokyo')
REPO = Path(__file__).resolve().parents[1]
# Financial targets only; Zaim propagation and trade jobs are separate operations.
PORTFOLIO_IDS = (
    'axa_life', 'sbi_index', 'mhi_stock', 'akatsuki_bond', 'bloomo',
    'sony_life', 'sony_life_chikage', 'sony_life_sovani', 'sony_life_sovani_kids',
    'sony_life_policy_loan', 'sony_life_chikage_policy_loan',
    'prudential_life', 'prudential_life_chikage',
    'prudential_life_policy_loan', 'prudential_life_chikage_policy_loan',
)
OPERATIONS = ('liquidity_weekly', 'tachibana_trade', 'akatsuki_zaim', 'bloomo_zaim')
SCOPES = {
    'portfolio': ('portfolio_accounts', 'portfolio_snapshots'),
    'liquidity': ('liquidity_accounts', 'liquidity_snapshots'),
}
REFERENCE_MARKERS = ('manual', 'reused', 'preserved', 'fallback', '手登録', '手入力', '転記')


def valid_day(value: Any) -> date | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = date.fromisoformat(value)
        return parsed if parsed.isoformat() == value else None
    except ValueError:
        return None


def finished_time(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
        return parsed.astimezone(JST) if parsed.tzinfo else None
    except ValueError:
        return None


def safe_ref(scope: str, ident: str) -> str:
    if scope == 'portfolio' and ident in PORTFOLIO_IDS:
        return ident
    return scope + '-' + hashlib.sha256(ident.encode()).hexdigest()[:12]


def paged(query: Any) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    offset = 0
    while True:
        page = query.range(offset, offset + 499).execute().data
        if not isinstance(page, list):
            raise ValueError('invalid_db_response')
        rows.extend(page)
        if len(page) < 500:
            return rows
        offset += 500


def read_database(client: Any, run_id: str | None = None) -> dict[str, Any]:
    """SELECT metadata only. No balances, names, free text, or storage are read."""
    result: dict[str, Any] = {}
    for scope, (accounts_table, snapshots_table) in SCOPES.items():
        record: dict[str, Any] = {'accounts_ok': False, 'snapshots_ok': False,
                                  'accounts': [], 'snapshots': []}
        result[scope] = record
        try:
            record['accounts'] = paged(client.table(accounts_table).select('id,kind')
                                       .eq('active', True).order('id'))
            record['excluded_non_balance'] = []
            if scope == 'liquidity':
                record['excluded_non_balance'] = [r['id'] for r in record['accounts'] if r.get('kind') == 'card']
                record['accounts'] = [r for r in record['accounts'] if r.get('kind') != 'card']
            record['accounts_ok'] = True
        except Exception:
            continue  # Do not serialize raw exceptions, URLs or credentials.
        ids = sorted({r['id'] for r in record['accounts'] if isinstance(r.get('id'), str)})
        try:
            for offset in range(0, len(ids), 100):
                record['snapshots'].extend(paged(
                    client.table(snapshots_table).select('account_id,as_of,source')
                    .in_('account_id', ids[offset:offset + 100])
                    .order('as_of', desc=True).order('account_id')))
            record['snapshots_ok'] = True
        except Exception:
            record['snapshots'] = []
    if run_id and re.fullmatch(r'[0-9a-f-]{36}',run_id):
        try:
            rows = (client.table('asset_618_display_checks')
                    .select('numeric_digest,matched_count,unresolved_count,checked_at').eq('run_id',run_id).limit(2).execute().data)
            result['display_check'] = rows[0] if isinstance(rows,list) and len(rows)==1 else None
        except Exception:
            result['display_check'] = None
            result['display_check_unavailable'] = True

    return result


def source_kind(value: Any) -> str:
    if not isinstance(value, str):
        return 'unknown'
    if 'manual' in value.lower():
        return 'manual_reference'
    if value in ('zaim', 'moneyforward', 'mf'):
        return 'imported'
    if value in ('weekly_web', 'weekly_web_loan', 'web'):
        return 'web_reported'
    return 'unknown'


def build_report(state: dict[str, Any], database: dict[str, Any] | None = None,
                 *, now: datetime | None = None, image_run: dict[str, Any] | None = None) -> dict[str, Any]:
    now = (now or datetime.now(JST)).astimezone(JST)
    monday = now.date() - timedelta(days=now.weekday())
    finished = finished_time(state.get('finished_at'))
    current = bool(finished and monday <= finished.date() <= now.date()
                   and finished <= now and state.get('iso_week') == now.strftime('%G-W%V'))
    sources = state.get('sources')
    state_valid = isinstance(sources, dict) and bool(sources)
    sources = sources if state_valid else {}
    items: list[dict[str, Any]] = []
    scope_verified = database is not None
    db_failures = 0
    for scope in SCOPES:
        data = (database or {}).get(scope, {})
        accounts_ok = data.get('accounts_ok') is True
        snapshots_ok = data.get('snapshots_ok') is True
        scope_verified = scope_verified and accounts_ok
        if database is not None:
            db_failures += int(not accounts_ok) + int(accounts_ok and not snapshots_ok)
        # An unavailable scope must not appear as an empty, successfully checked scope.
        ids = sorted({r['id'] for r in data.get('accounts', [])
                      if isinstance(r, dict) and isinstance(r.get('id'), str)}) if accounts_ok else (
                          list(PORTFOLIO_IDS) if scope == 'portfolio' else [])
        latest: dict[str, dict[str, Any]] = {}
        for row in data.get('snapshots', []) if snapshots_ok else []:
            if not isinstance(row, dict):
                continue
            ident, as_of = row.get('account_id'), valid_day(row.get('as_of'))
            if ident in ids and as_of and (ident not in latest or as_of > valid_day(latest[ident]['as_of'])):
                latest[ident] = row
        for ident in ids:
            rec = sources.get(ident)
            rec = rec if isinstance(rec, dict) else {}
            status = rec.get('status')
            # Legacy runners can preserve or reuse an old ok, including after a later failure.
            provenance = ' '.join(str(rec.get(k) or '') for k in ('source', 'note', 'reason')).lower()
            reference = any(marker in provenance for marker in REFERENCE_MARKERS)
            collected = ('failed' if status == 'error' else 'skipped' if status in ('skip', 'skipped')
                         else 'reference' if status == 'reference' or (status == 'ok' and reference)
                         else 'reported_ok' if status == 'ok' and current and state.get('cloud_only') is not True
                         else 'unverified')
            row = latest.get(ident)
            as_of = valid_day(row.get('as_of')) if row else None
            kind = source_kind(row.get('source')) if row else 'unknown'
            if collected == 'reported_ok' and kind == 'manual_reference':
                collected = 'reference'
            db_status = ('not_checked' if database is None else 'unavailable' if not snapshots_ok
                         else 'missing' if not row else 'invalid_date' if as_of > now.date()
                         else 'current_week' if as_of >= monday else 'older')
            items.append({'ref': safe_ref(scope, ident), 'scope': scope,
                          'collection': collected, 'database': db_status,
                          'source_as_of': as_of.isoformat() if as_of else None,
                          'source_kind': kind})
    counts = dict(Counter(item['collection'] for item in items))
    db_counts = dict(Counter(item['database'] for item in items))
    operations = {key: (sources.get(key, {}).get('status')
                       if isinstance(sources.get(key), dict) else None) for key in OPERATIONS}
    # Only fixed status words leave this boundary; unknown source values are not copied.
    operations = {key: value if value in ('ok', 'error', 'skip', 'skipped') else 'unverified'
                  for key, value in operations.items()}
    complete = bool(items and current and scope_verified and not db_failures
                    and all(i['collection'] == 'reported_ok' and i['database'] == 'current_week'
                            for i in items))
    report = {'schema_version': 1, 'mode': 'draft_only',
              'checked_at': now.isoformat(timespec='seconds'),
              'collection_finished_at': finished.isoformat(timespec='seconds') if finished else None,
              'result_period': 'current_week' if current else 'outdated_or_unverified',
              'state_valid': state_valid, 'scope_verified': bool(scope_verified),
              'collection_mode': 'cloud_only' if state.get('cloud_only') is True else 'local_or_unspecified',
              'overall': 'metadata_consistent' if complete else 'partial_or_unverified',
              'target_count': len(items), 'collection_counts': counts,
              'database_counts': db_counts, 'database_read_failures': db_failures,
              'current_write': 'not_verified', 'kurashift_display': 'not_verified',
              'image_update': 'not_requested_not_checked',
              'items': items, 'operations': operations}
    context = state.get('asset_618')
    if isinstance(context,dict) and isinstance(context.get('numeric_readbacks'),dict):
        from jarvis_asset_618_readback import context_digest
        checks = context['numeric_readbacks']
        flat = [r for table in SCOPES.values() if isinstance(checks.get(table[1]),dict) for r in checks[table[1]].values() if isinstance(r,dict)]
        valid = [r for r in flat if r.get('status') == 'verified' and re.fullmatch(r'[a-f0-9]{64}',str(r.get('row_digest') or '')) and valid_day(r.get('record_as_of')) and finished_time(r.get('checked_at')) and finished_time(r['checked_at']) <= now]
        report['numeric_readback'] = {'verified':len(valid),'unverified':len(flat)-len(valid)}
        report['current_write'] = 'readback_recorded' if valid else 'not_verified'
        receipt = (database or {}).get('display_check')
        try:
            matches = (isinstance(receipt,dict) and receipt.get('numeric_digest') == context_digest(checks)
                       and type(receipt.get('matched_count')) is int and 0 < receipt['matched_count'] <= len(valid)
                       and type(receipt.get('unresolved_count')) is int and receipt['unresolved_count'] >= 0
                       and finished_time(receipt.get('checked_at')) and finished_time(receipt['checked_at']) <= now)
        except (ValueError,TypeError,KeyError):
            matches = False
        if matches:
            report['kurashift_display'] = 'checked_for_run'
            report['display_check'] = {k:receipt[k] for k in ('matched_count','unresolved_count','checked_at')}
    if isinstance(image_run,dict) and image_run.get('kind') == 'unavailable':
        report['image_update'] = 'unavailable'
    if isinstance(image_run,dict) and image_run.get('kind') == 'evidence_publish':
        rows = image_run.get('image_results')
        if isinstance(rows,list) and rows and all(isinstance(r,dict) for r in rows):
            report['image_result'] = {'updated':sum(r.get('status')=='ok' for r in rows), 'failed':sum(r.get('status')=='error' for r in rows)}
            report['image_update'] = 'readback_recorded_for_image_run'
    report['drafts'] = make_drafts(report)
    return report


def make_drafts(report: dict[str, Any]) -> dict[str, str]:
    counts, db = report['collection_counts'], report['database_counts']
    drafts = {'report': '\n'.join([
        '【報告案・未送信】618 資産記録',
        '収集記録：今週' if report['result_period'] == 'current_week' else '収集記録：以前または日時不明',
        f"収集報告ok {counts.get('reported_ok', 0)}件／参考値 {counts.get('reference', 0)}件",
        f"未取得 {counts.get('skipped', 0)}件／エラー {counts.get('failed', 0)}件／未検証 {counts.get('unverified', 0)}件",
        f"DBに今週の記録日あり {db.get('current_week', 0)}件",
        f"数値DB読戻し：{report['numeric_readback']['verified']}件記録済み" if report.get('numeric_readback') else '今回の書込は未検証（数値DB）',
        f"画像更新：{report['image_result']['updated']}件／失敗{report['image_result']['failed']}件" if report.get('image_result') else '画像更新：記録の読取失敗' if report.get('image_update') == 'unavailable' else '画像更新：未依頼・未確認',
        f"当該実行の保存確認欄：{report['display_check']['matched_count']}件一致／未確認{report['display_check']['unresolved_count']}件" if report.get('display_check') else 'KURASHIFT反映：未検証',
        '対象一覧：DB確認済み' if report['scope_verified'] else '対象一覧：未検証（件数は暫定）',
    ])}
    if report['overall'] != 'metadata_consistent':
        drafts['consult'] = '\n'.join([
            '【相談案・未送信】618 資産記録',
            '未取得・参考値・基準日の古さ・未検証の対象が残っています。',
            '次: 人判断のみ（必要な対象を音声・チャットで取り直し依頼）',
            '担当メモ: 618。収集結果とDB記録を照合し、未取得対象だけ再確認。',
            '橋渡し: 松野さんの依頼を受けて取り直し。Slackを起動に使わない。',
        ])
    if not report['state_valid'] or report['database_read_failures'] or counts.get('failed', 0) or report.get('image_result', {}).get('failed', 0):
        drafts['ops'] = '\n'.join([
            '【障害案・未送信】618 資産記録',
            f"収集エラー {counts.get('failed', 0)}件／DB読取失敗 {report['database_read_failures']}件",
            f"画像更新失敗 {report.get('image_result', {}).get('failed', 0)}件",
            '実行記録：確認済み' if report['state_valid'] else '実行記録：読取不可・形式不正',
            '取得元の例外本文は非表示。金融操作・再取得・投稿は行っていません。',
        ])
    return drafts


def db_client(env_file: Path | None = None) -> Any:
    # Credentials are read only for this explicitly requested connection check.
    config: dict[str, Any] = {}
    if env_file:
        # Same single-line syntax as the existing weekly env loader; never source a shell.
        for raw in env_file.read_text(encoding='utf-8').splitlines():
            line = raw.strip()
            if line.startswith('export '):
                line = line[7:].strip()
            name, separator, value = line.partition('=')
            if separator and name.strip() in ('JARVIS_SUPABASE_URL', 'JARVIS_SUPABASE_SERVICE_ROLE_KEY'):
                value = value.strip()
                if len(value) >= 2 and value[0] == value[-1] and value[0] in '"\'':
                    value = value[1:-1]
                config[name.strip()] = value
    from supabase import create_client
    keys = ('JARVIS_SUPABASE_URL', 'JARVIS_SUPABASE_SERVICE_ROLE_KEY')
    url, key = [os.environ.get(k) or config.get(k) for k in keys]
    if not url or not key:
        raise ValueError('db_connection_unavailable')
    for logger in ('httpx', 'httpcore'):
        logging.getLogger(logger).setLevel(logging.WARNING)
    return create_client(url, key)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state', type=Path, default=REPO / '.jarvis_state/portfolio_weekly.json')
    parser.add_argument('--read-db', action='store_true', help='Read account/date/source metadata only')
    parser.add_argument('--image-run', type=Path, help='Optional image publishing run record')
    parser.add_argument('--env-file', type=Path, help='Optional private connection file (never printed)')
    parser.add_argument('--out', type=Path, help='Save sanitized report.json and draft files locally')
    args = parser.parse_args(argv)
    try:
        state = json.loads(args.state.read_text(encoding='utf-8'))
        if not isinstance(state, dict):
            raise ValueError('invalid_state')
    except (OSError, ValueError):
        state = {}
    database = None
    if args.read_db:
        try:
            database = read_database(db_client(args.env_file), (state.get("asset_618") or {}).get("run_id"))
        except Exception:
            database = {}  # Explicit DB failures, never fall back to a success claim.
    try:
        image_run = json.loads(args.image_run.read_text(encoding="utf-8")) if args.image_run else None
    except (OSError,ValueError):
        image_run = {"kind":"unavailable"}
    report = build_report(state, database, image_run=image_run)
    if args.out:
        args.out.mkdir(parents=True, exist_ok=True)
        (args.out / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        drafts = '\n\n'.join('#' + channel + '\n' + body for channel, body in report['drafts'].items())
        (args.out / 'slack_drafts.txt').write_text(drafts + '\n', encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report['state_valid'] and not report['database_read_failures'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
