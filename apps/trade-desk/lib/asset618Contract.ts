export const EVIDENCE_BUCKET = 'asset-evidence';
export const TABLES = ['portfolio_snapshots', 'liquidity_snapshots'] as const;
export type NumericTable = typeof TABLES[number];
export const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
export const ID = /^[a-zA-Z0-9_-]{1,100}$/;
export const SHA = /^[a-f0-9]{64}$/;
export function decimalText(value: unknown): string {
  if (typeof value !== 'string' && typeof value !== 'number') throw new Error('invalid number');
  const text = String(value);
  if (!/^-?\d+(\.\d+)?$/.test(text)) throw new Error('invalid number');
  const negative = text.startsWith('-');
  const [whole, fraction = ''] = text.replace(/^-/, '').split('.');
  const trimmed = whole.replace(/^0+(?=\d)/, '') + (fraction.replace(/0+$/, '') ? '.' + fraction.replace(/0+$/, '') : '');
  return (negative && trimmed !== '0' ? '-' : '') + trimmed;
}
export type NumericValue = { table: NumericTable; account_id: string; as_of: string; value: string; source: string };
export function rowText(row: NumericValue): string {
  if (!TABLES.includes(row.table) || !ID.test(row.account_id) || !/^\d{4}-\d\d-\d\d$/.test(row.as_of) || row.source.includes('|') || row.source.length > 100) throw new Error('invalid snapshot');
  const parsed = new Date(row.as_of + 'T00:00:00Z');
  if (Number.isNaN(parsed.getTime()) || parsed.toISOString().slice(0, 10) !== row.as_of) throw new Error('invalid date');
  return [row.table, row.account_id, row.as_of, decimalText(row.value), row.source].join('|');
}
export function evidenceState(row: {storage_path: string | null; last_attempt_status: string}): string {
  if (!row.storage_path) return row.last_attempt_status === 'pending' ? '更新確認待ち・正常画像なし' : '正常画像なし';
  if (row.last_attempt_status === 'pending') return '更新確認待ち・前回の正常画像を保持';
  if (row.last_attempt_status === 'failed') return '今回の更新失敗・前回の正常画像を保持';
  return '保存済みの正常画像';
}
export function evidencePath(row: {owner_id: string; account_scope: string; account_id: string; contract_key: string; view_key: string; active_slot: string | null}): string | null {
  if (!UUID.test(row.owner_id) || !['portfolio','liquidity'].includes(row.account_scope) || ![row.account_id,row.contract_key,row.view_key].every(x => ID.test(x)) || !['a','b'].includes(row.active_slot || '')) return null;
  return `618/latest/${row.owner_id}/${row.account_scope}/${row.account_id}/${row.contract_key}/${row.view_key}.${row.active_slot}.png`;
}
