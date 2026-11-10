import test from 'node:test';
import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { createRaimoAuthGateway } from '../lib/raimoAuthGateway.ts';
import { normalizeMemberNo, normalizeName, rosterHash, matchPending } from '../lib/rosterMatch.ts';

const script = fileURLToPath(new URL('../../../scripts/kamiooya_roster_sync.py', import.meta.url));

test('正規化: 全角・空白・先頭0・中黒の違いは同じ扱い', () => {
  assert.equal(normalizeMemberNo('０１２３'), '123');
  assert.equal(normalizeMemberNo('A-12'), 'a12');
  assert.equal(normalizeName('山田　太郎'), '山田太郎');
  assert.equal(normalizeName('ジョン・スミス'), 'ジョンスミス');
});

test('同期スクリプト（Python）と照合（TS）のハッシュが一致する', async () => {
  const py = `import importlib.util,sys,json
spec=importlib.util.spec_from_file_location('s',${JSON.stringify(script)});m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
rows=[['説明'],['会員番号','姓','名'],['STEP'],['０１２３','山田','太郎'],['456','佐藤',''],['','空','行']]
print(json.dumps(sorted([list(x) for x in m.hashes_from_rows(rows)])))`;
  let out;
  try { out = JSON.parse(execFileSync('python3', ['-I', '-c', py], { encoding: 'utf8' })); } catch (e) { if (e.code === 'ENOENT') return; throw e; }
  const expected = [['no', await rosterHash('no', '123')], ['no', await rosterHash('no', '456')],
    ['no_name', await rosterHash('no_name', '123', '山田 太郎')], ['no_name', await rosterHash('no_name', '456', '佐藤')]].sort((a, b) => (a[0] < b[0] ? -1 : a[0] > b[0] ? 1 : a[1] < b[1] ? -1 : 1));
  assert.deepEqual(out, expected);
});

test('照合: 一致／番号だけ／名簿になし／同じ番号が複数／空', async () => {
  const roster = new Set([await rosterHash('no', '123'), await rosterHash('no_name', '123', '山田太郎'), await rosterHash('no', '456')]);
  const asked = [];
  const r = await matchPending([
    { id: 'a', member_no: '0123', name: '山田 太郎' },
    { id: 'b', member_no: '456', name: '別人' },
    { id: 'c', member_no: '789', name: '鈴木' },
    { id: 'd', member_no: '111', name: 'x' }, { id: 'e', member_no: '111', name: 'y' },
    { id: 'f', member_no: '', name: '名前だけ' },
  ], async h => { asked.push(...h); return new Set(h.filter(x => roster.has(x))); });
  assert.deepEqual(r, { a: 'match', b: 'number_only', c: 'none', d: 'duplicate', e: 'duplicate', f: 'missing' });
  assert.equal(asked.length, 6); // a,b,c の 2 個ずつだけ問い合わせる（名簿全件は読まない）
});

test('照合 API は「管理者」かつ「スイッチで見える人」だけ。名簿の中身は返さない', async () => {
  const origin = 'https://offline.example';
  const users = { o1: { id: 'o1', email: 'owner@example.test', role: 'master_admin', status: 'approved', authVersion: '1' },
    a1: { id: 'a1', email: 'admin@example.test', role: 'admin', status: 'approved', authVersion: '1' } };
  const tokens = new Map([['a'.repeat(64), 'o1'], ['b'.repeat(64), 'a1']]);
  const pend = { users: [{ id: 'p1', member_no: '123', name: '山田太郎', email: 'p@example.test' }] };
  const rows = new Set([await rosterHash('no', '123'), await rosterHash('no_name', '123', '山田太郎')]);
  const handler = createRaimoAuthGateway({ origin, member: async id => users[id] || null,
    sessions: { get: async t => tokens.has(t) ? { uid: tokens.get(t), authVersion: '1', expires: Date.now() + 60000 } : null, put: async () => {}, delete: async () => {} },
    authenticate: async () => null, allowLogin: async () => true, chatOwner: async () => null,
    forward: async (m, p) => { assert.equal(p, '/admin/users/pending'); return pend; }, attachmentSession: async () => ({}),
    featureFlags: async () => [{ feature: 'auto_approval', stage: 'owner', owner_ids: ['owner@example.test'] }],
    roster: { has: async h => new Set(h.filter(x => rows.has(x))), meta: async () => ({ row_count: 2723, synced_at: '2026-11-10T14:00:00Z' }) } });
  const post = t => handler(new Request('https://g.example/admin/users/pending/roster-match', { method: 'POST', headers: { Origin: origin, Authorization: 'Bearer ' + t }, body: '{}' }));
  const ok = await post('a'.repeat(64));
  assert.equal(ok.status, 200);
  assert.deepEqual(await ok.json(), { matches: { p1: 'match' }, roster_count: 2723, synced_at: '2026-11-10T14:00:00Z' });
  assert.equal((await post('b'.repeat(64))).status, 404); // 管理者でも名指しが無い
});
