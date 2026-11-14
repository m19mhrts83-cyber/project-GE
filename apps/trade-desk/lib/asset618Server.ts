import { createHash } from 'node:crypto';
import type { SupabaseClient } from '@supabase/supabase-js';
import { decimalText, ID, rowText, SHA, TABLES, UUID, type NumericValue } from './asset618Contract';

export const digest = (text: string) => createHash('sha256').update(text).digest('hex');
export type Readback = {status: string; record_as_of?: string; source_as_of?: string | null; row_digest?: string};
export type Context = {run_id: string; started_at?: string; target_ids: string[]; excluded_targets?: string[]; held_targets?: string[]; numeric_readbacks?: Record<string, Record<string, Readback>>};
export type DisplayRow = NumericValue & {expected_digest: string; label: string; matches: boolean; source_as_of: string | null};
export type NumericStatus = {state: 'ready'; context: Context; rows: DisplayRow[]; unresolved: number; numeric_digest: string; receipt: {checked_at: string; matched_count: number; unresolved_count: number; numeric_digest: string} | null} | {state: 'unavailable' | 'not_owner' | 'no_run'};
export async function assetOwner(client: SupabaseClient, userId: string): Promise<boolean | null> {
  try {
    const {data,error} = await client.from('asset_evidence_owners').select('user_id').eq('user_id',userId).limit(1);
    return error ? null : Boolean(data?.length);
  } catch { return null; }
}
export function contextText(context: Context): string {
  const lines: string[] = [];
  for (const table of TABLES) for (const [id, check] of Object.entries(context.numeric_readbacks?.[table] || {})) {
    if (!ID.test(id) || !['verified','pending','not_collected'].includes(check.status) || (check.row_digest && !SHA.test(check.row_digest))) throw new Error('invalid readback');
    lines.push([table,id,check.status,check.row_digest || ''].join('|'));
  }
  return lines.sort().join('\n');
}
export async function loadNumericStatus(client: SupabaseClient, userId: string): Promise<NumericStatus> {
  const owner = await assetOwner(client,userId);
  if (owner === null) return {state:'unavailable'};
  if (!owner) return {state:'not_owner'};
  try {
    const {data,error} = await client.from('sync_meta').select('value').eq('key','portfolio_weekly_summary').limit(1);
    if (error) return {state:'unavailable'};
    const summary = typeof data?.[0]?.value === 'string' ? JSON.parse(data[0].value) : data?.[0]?.value;
    const context = summary?.asset_618 as Context | undefined;
    if (!context || !UUID.test(context.run_id) || !Array.isArray(context.target_ids) || !context.target_ids.every(x => typeof x === 'string' && ID.test(x))) return {state:'no_run'};
    const specs = TABLES.flatMap(table => Object.entries(context.numeric_readbacks?.[table] || {}).map(([account_id,check]) => ({table,account_id,check})));
    if (specs.length > 256) return {state:'unavailable'};
    const numeric_digest = digest(contextText(context));
    const actual = new Map<string, NumericValue>();
    const labels = new Map<string, string>();
    const queries = TABLES.map(async table => {
      const wanted = specs.filter(x => x.table === table && x.check.status === 'verified');
      if (!wanted.length) return;
      const ids = [...new Set(wanted.map(x => x.account_id))];
      const dates = wanted.map(x => x.check.record_as_of || '').sort();
      if (!dates[0] || !dates.every(x => /^\d{4}-\d\d-\d\d$/.test(x))) throw new Error('invalid date');
      const valueKey = table === 'portfolio_snapshots' ? 'value_jpy' : 'balance_jpy';
      const [{data: snapshots,error},{data: accounts}] = await Promise.all([
        client.from(table).select(`account_id,as_of,${valueKey},source`).in('account_id',ids).gte('as_of',dates[0]).lte('as_of',dates[dates.length-1]).limit(10000),
        client.from(table === 'portfolio_snapshots' ? 'portfolio_accounts' : 'liquidity_accounts').select('id,name').in('id',ids),
      ]);
      for (const account of accounts || []) labels.set(`${table}|${account.id}`,account.name);
      if (error) throw new Error('snapshot unavailable');
      for (const snapshot of snapshots || []) {
        const r = snapshot as unknown as Record<string, unknown>;
        const value: NumericValue = {table,account_id:String(r.account_id),as_of:String(r.as_of),value:decimalText(r[valueKey]),source:String(r.source || '')};
        actual.set(`${table}|${value.account_id}|${value.as_of}`,value);
      }
    });
    await Promise.all(queries);
    const rows: DisplayRow[] = [];
    let unresolved = 0;
    const specified = new Set<string>();
    for (const spec of specs) {
      specified.add(spec.account_id);
      const row = actual.get(`${spec.table}|${spec.account_id}|${spec.check.record_as_of}`);
      if (!row || spec.check.status !== 'verified' || !SHA.test(spec.check.row_digest || '')) { unresolved++; continue; }
      const matches = digest(rowText(row)) === spec.check.row_digest;
      if (!matches) unresolved++;
      rows.push({...row,label:labels.get(`${spec.table}|${spec.account_id}`) || spec.account_id,expected_digest:spec.check.row_digest!,matches,source_as_of:spec.check.source_as_of || null});
    }
    for (const id of context.target_ids) {
      if (context.excluded_targets?.includes(id) || ['akatsuki_zaim','bloomo_zaim'].includes(id)) continue;
      if (id === 'liquidity_weekly') { if (!specs.some(x => x.table === 'liquidity_snapshots')) unresolved++; }
      else if (!specified.has(id)) unresolved++;
    }
    const {data: receipts,error: receiptError} = await client.from('asset_618_display_checks').select('checked_at,matched_count,unresolved_count,numeric_digest').eq('owner_id',userId).eq('run_id',context.run_id).limit(1);
    if (receiptError) return {state:'unavailable'};
    return {state:'ready',context,rows,unresolved,numeric_digest,receipt:receipts?.[0] || null};
  } catch { return {state:'unavailable'}; }
}

export async function confirmDisplay(client: SupabaseClient, userId: string, body: unknown): Promise<{status: number; body: Record<string, unknown>}> {
  const status = await loadNumericStatus(client,userId);
  if (status.state !== 'ready') return {status: status.state === 'not_owner' ? 403 : 503,body:{error:'照合に必要な記録を取得できません'}};
  const input = body as {run_id?: unknown; rows?: unknown};
  if (!input || input.run_id !== status.context.run_id || !Array.isArray(input.rows) || input.rows.length > 256) return {status:409,body:{error:'実行記録が変わりました。再読込してください'}};
  const expected = status.rows.filter(x => x.matches);
  if (!expected.length || status.rows.some(x => !x.matches) || input.rows.length !== expected.length) return {status:409,body:{error:'保存結果と現在のDBが一致していません'}};
  try {
    const received = (input.rows as NumericValue[]).map(row => [row.table,row.account_id,digest(rowText(row))].join('|')).sort();
    const wanted = expected.map(row => [row.table,row.account_id,row.expected_digest].join('|')).sort();
    if (JSON.stringify(received) !== JSON.stringify(wanted)) return {status:409,body:{error:'画面の値と保存結果が一致していません'}};
    const checked_at = new Date().toISOString();
    const {error} = await client.from('asset_618_display_checks').upsert({owner_id:userId,run_id:status.context.run_id,numeric_digest:status.numeric_digest,matched_count:expected.length,unresolved_count:status.unresolved,checked_at},{onConflict:'owner_id,run_id'});
    if (error) throw new Error('receipt failed');
    return {status:200,body:{matched:expected.length,unresolved:status.unresolved,checked_at}};
  } catch { return {status:503,body:{error:'照合結果の記録に失敗しました'}}; }
}
