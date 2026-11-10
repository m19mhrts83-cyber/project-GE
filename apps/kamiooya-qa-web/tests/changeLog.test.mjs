import test from 'node:test';
import assert from 'node:assert/strict';
import { createRaimoAuthGateway } from '../lib/raimoAuthGateway.ts';
import { publicChangeLog } from '../lib/changeLog.ts';

const origin = 'https://offline.example';
const owner = { id: 'o1', email: 'owner@example.test', role: 'user', status: 'approved', authVersion: '1' };
const other = { id: 'u2', email: 'member@example.test', role: 'user', status: 'approved', authVersion: '1' };
function gateway(stage) {
  const tokens = new Map([['a'.repeat(64), 'o1'], ['b'.repeat(64), 'u2']]);
  const handler = createRaimoAuthGateway({ origin, member: async id => ({ o1: owner, u2: other })[id] || null,
    sessions: { get: async t => tokens.has(t) ? { uid: tokens.get(t), authVersion: '1', expires: Date.now() + 60000 } : null, put: async () => {}, delete: async () => {} },
    authenticate: async () => null, allowLogin: async () => true, chatOwner: async () => null, forward: async () => ({}), attachmentSession: async () => ({}),
    featureFlags: async () => [{ feature: 'change_log', stage, owner_ids: ['owner@example.test'] }],
    listChangeLog: async () => [{ id: 9, visible: true, released_on: '2026-11-11', title: '動画の題名から番号を消しました', body: '根拠の一覧が読みやすくなります。', trigger: '松野さんのご意見' }] });
  return t => handler(new Request('https://g.example/change-log', { headers: { Origin: origin, Authorization: 'Bearer ' + t } }));
}

test('改善履歴: スイッチで見える人だけが読める。id や表示フラグは返さない', async () => {
  const get = gateway('owner');
  const ok = await get('a'.repeat(64));
  assert.equal(ok.status, 200);
  assert.deepEqual(await ok.json(), { entries: [{ released_on: '2026-11-11', title: '動画の題名から番号を消しました', body: '根拠の一覧が読みやすくなります。', trigger: '松野さんのご意見' }] });
  assert.equal((await get('b'.repeat(64))).status, 404);
  assert.equal((await gateway('off')('a'.repeat(64))).status, 404);
  assert.equal((await gateway('all')('b'.repeat(64))).status, 200);
});

test('改善履歴: 壊れた行は落とし、長さを切る', () => {
  assert.deepEqual(publicChangeLog([{ title: '' }, { released_on: 'x', title: 't'.repeat(200) }]).map(r => [r.released_on, r.title.length]), [['', 120]]);
  assert.deepEqual(publicChangeLog(null), []);
});
