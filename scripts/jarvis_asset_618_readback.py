"""Verify the exact numeric row after persistence. Never logs amounts or raw exceptions."""
from __future__ import annotations
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import re
from typing import Any

TABLES = {'portfolio_snapshots': 'value_jpy', 'liquidity_snapshots': 'balance_jpy'}

class ReadbackError(RuntimeError):
    pass


def decimal_text(value: Any) -> str:
    if isinstance(value, bool) or value is None:
        raise ReadbackError('invalid_numeric_value')
    try:
        number = Decimal(str(value))
        if not number.is_finite():
            raise ValueError()
        result = format(number, 'f').rstrip('0').rstrip('.') if '.' in format(number, 'f') else format(number, 'f')
        return '0' if number == 0 else result
    except (InvalidOperation, ValueError, TypeError):
        raise ReadbackError('invalid_numeric_value') from None


def row_digest(table: str, row: dict[str, Any]) -> str:
    if table not in TABLES or not re.fullmatch(r'[a-zA-Z0-9_-]{1,100}', str(row.get('account_id') or '')):
        raise ReadbackError('invalid_snapshot_identity')
    day = row.get('as_of')
    try:
        if date.fromisoformat(day).isoformat() != day:
            raise ValueError()
    except (ValueError, TypeError):
        raise ReadbackError('invalid_snapshot_date') from None
    source = row.get('source') or ''
    if not isinstance(source, str) or '|' in source or len(source) > 100:
        raise ReadbackError('invalid_snapshot_source')
    raw = '|'.join((table, row['account_id'], day, decimal_text(row[TABLES[table]]), source))
    return hashlib.sha256(raw.encode()).hexdigest()


def verify_snapshot(client: Any, table: str, expected: dict[str, Any], *, source_as_of: str | None = None) -> dict[str, Any]:
    digest = row_digest(table, expected)
    try:
        columns = ['account_id', 'as_of', TABLES[table], 'source']
        if 'cost_jpy' in expected:
            columns.append('cost_jpy')
        rows = (client.table(table).select(','.join(columns)).eq('account_id', expected['account_id'])
                .eq('as_of', expected['as_of']).limit(2).execute().data)
        if not isinstance(rows, list) or len(rows) != 1 or row_digest(table, rows[0]) != digest:
            raise ValueError()
        if 'cost_jpy' in expected and decimal_text(rows[0].get('cost_jpy')) != decimal_text(expected['cost_jpy']):
            raise ValueError()
    except Exception:
        raise ReadbackError('numeric_readback_failed_or_mismatched') from None
    return {'status': 'verified', 'record_as_of': expected['as_of'],
            'source_as_of': source_as_of, 'source_as_of_verified': source_as_of is not None,
            'row_digest': digest, 'checked_at': datetime.now(timezone.utc).isoformat(timespec='seconds')}


def context_digest(checks: dict) -> str:
    lines = []
    for table in TABLES:
        for aid, check in checks.get(table, {}).items():
            lines.append('|'.join((table, aid, check['status'], check.get('row_digest') or '')))
    return hashlib.sha256('\n'.join(sorted(lines)).encode()).hexdigest()
