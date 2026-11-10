import test from 'node:test';
import assert from 'node:assert/strict';
import { createRaimoAuthGateway } from '../lib/raimoAuthGateway.ts';
import { parseFeedback, feedbackRow } from '../lib/answerFeedback.ts';

const origin = 'https://offline.example';
const owner = { id: 'o1', email: 'owner@example.test', role: 'master_admin', status: 'approved', authVersion: '1' };
const admin = { id: 'a1', email: 'admin@example.test', role: 'admin', status: 'approved', authVersion: '1' };
const messages = [{ id: 'm1', role: 'user', content: '火災保険 保険料' }, { id: 'm2', role: 'assistant', content: '回答本文' }];
function setup(stage = 'owner') {
  const saved = [], tokens = new Map([['a'.repeat(64), 'o1'], ['b'.repeat(64), 'a1']]);
  const handler = createRaimoAuthGateway({ origin, member: async id => ({ o1: owner, a1: admin })[id] || null,
    sessions: { get: async t => tokens.has(t) ? { uid: tokens.get(t), authVersion: '1', expires: Date.now() + 60000 } : null, put: async () => {}, delete: async () => {} },
    authenticate: async () => null, allowLogin: async () => true,
    chatOwner: async id => id === 'c1' ? 'o1' : id === 'c2' ? 'a1' : 'x',
    forward: async (method, path) => { assert.equal(method, 'GET'); return { session: {}, messages: path.endsWith('/c1') || path.endsWith('/c2') ? messages : [] }; },
    attachmentSession: async () => ({}),
    featureFlags: async () => [{ feature: 'answer_feedback', stage, owner_ids: ['owner@example.test'], reviewer_ids: [] }],
    saveFeedback: async row => { saved.push(row); } });
  const post = (t, body) => handler(new Request('https://g.example/answer-feedback', { method: 'POST', headers: { Origin: origin, Authorization: 'Bearer ' + t }, body: JSON.stringify(body) }));
  return { saved, post };
}

test('対象者は評価を保存でき、本文はサーバーがチャットから引く', async () => {
  const s = setup();
  const r = await s.post('a'.repeat(64), { chat_id: 'c1', message_id: 'm2', rating: 'great', comment: ' 分かりやすい ', answer: '偽の本文', user_id: 'other' });
  assert.equal(r.status, 200);
  assert.equal(s.saved.length, 1);
  assert.deepEqual({ ...s.saved[0], updated_at: 'x' }, { user_id: 'o1', chat_id: 'c1', message_id: 'm2', rating: 'great', comment: '分かりやすい', question: '火災保険 保険料', answer: '回答本文', updated_at: 'x' });
});

test('スイッチで見えない管理者には 404、他人のチャットは 403、質問への評価は 404', async () => {
  const s = setup();
  assert.equal((await s.post('b'.repeat(64), { chat_id: 'c2', message_id: 'm2', rating: 'good' })).status, 404);
  assert.equal((await s.post('a'.repeat(64), { chat_id: 'c3', message_id: 'm2', rating: 'good' })).status, 403);
  assert.equal((await s.post('a'.repeat(64), { chat_id: 'c1', message_id: 'm1', rating: 'good' })).status, 404);
  assert.equal(s.saved.length, 0);
  const off = setup('off');
  assert.equal((await off.post('a'.repeat(64), { chat_id: 'c1', message_id: 'm2', rating: 'good' })).status, 404);
});

test('入力の検査', () => {
  assert.throws(() => parseFeedback({ chat_id: 'c1', message_id: 'm2', rating: 'meh' }));
  assert.throws(() => parseFeedback({ chat_id: 'c/1', message_id: 'm2', rating: 'good' }));
  assert.throws(() => parseFeedback({ chat_id: 'c1', message_id: 'm2', rating: 'good', comment: 'x'.repeat(1001) }));
  assert.equal(parseFeedback({ chat_id: 'c1', message_id: 'm2', rating: 'bad', comment: 5 }).comment, '');
  assert.throws(() => feedbackRow('o1', { chat_id: 'c1', message_id: 'zz', rating: 'good', comment: '' }, messages), e => e.status === 404);
});
