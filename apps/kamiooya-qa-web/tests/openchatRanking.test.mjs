import test from 'node:test';
import assert from 'node:assert/strict';
import { shapeOpenchatRound } from '../lib/openchatRanking.ts';
import { createRaimoAuthGateway } from '../lib/raimoAuthGateway.ts';

const round = { id: 'r20261116', created_at: '2026-11-16T00:00:00Z', period_days: 120,
  ranking: [{ topic: '自己資金の目安', count: 12, people: 9, replies: 40, recent: 3, sender_name: 'X',
    chats: [{ chat: '33融資相談G', n: 8 }, { chat: '02初心者G', n: 4 }],
    examples: [{ chat: '33融資相談G', d: '2026-11-10', text: '自己資金は？', u: 'hash' }, {}, {}, {}] }],
  by_chat: [{ chat: '33融資相談G', questions: 480, people: 70, top: [{ topic: '自己資金の目安', count: 8, people: 6, examples: ['a', 'b', 'c'] }] }],
  stats: { posts: 10785, questions: 2500, people: 160, chats: 30 } };

test('画面に返すのは決まった項目だけ', () => {
  const s = shapeOpenchatRound(round);
  assert.equal(s.ranking[0].examples.length, 3);
  assert.equal(s.by_chat[0].top[0].examples.length, 2);
  const text = JSON.stringify(s);
  assert.equal(text.includes('sender_name'), false);
  assert.equal(text.includes('hash'), false);
  assert.equal(s.stats.questions, 2500);
});

test('スイッチ openchat_ranking で見える管理者だけが一覧を使える', async () => {
  const origin = 'https://offline.example';
  const members = { o1: { id: 'o1', email: 'owner@example.test', role: 'master_admin', status: 'approved', authVersion: '1' },
    a1: { id: 'a1', email: 'admin@example.test', role: 'admin', status: 'approved', authVersion: '1' } };
  const sessions = new Map([['a'.repeat(64), { uid: 'o1', authVersion: '1', expires: Date.now() + 60000 }], ['b'.repeat(64), { uid: 'a1', authVersion: '1', expires: Date.now() + 60000 }]]);
  const handler = createRaimoAuthGateway({ origin, member: async id => members[id] || null,
    sessions: { get: async t => sessions.get(t) || null, put: async () => {}, delete: async () => {} },
    authenticate: async () => null, allowLogin: async () => true, chatOwner: async () => null,
    forward: async () => { throw new Error('should not forward'); }, attachmentSession: async () => ({}),
    featureFlags: async () => [{ feature: 'openchat_ranking', stage: 'owner', owner_ids: ['o1'], reviewer_ids: [] }],
    openchatRankings: async () => [round] });
  const post = (t) => handler(new Request('https://g.example/admin/openchat-ranking/list', { method: 'POST', headers: { Origin: origin, Authorization: 'Bearer ' + t, 'Content-Type': 'application/json' }, body: '{}' }));
  assert.equal((await post('b'.repeat(64))).status, 404);
  const ok = await (await post('a'.repeat(64))).json();
  assert.equal(ok.latest.ranking[0].topic, '自己資金の目安');
  assert.equal(ok.latest.by_chat[0].chat, '33融資相談G');
});
