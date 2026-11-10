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
  assert.deepEqual({ ...s.saved[0], updated_at: 'x' }, { user_id: 'o1', chat_id: 'c1', message_id: 'm2', rating: 'great', reasons: [], comment: '分かりやすい', question: '火災保険 保険料', answer: '回答本文', updated_at: 'x' });
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

test('評価の一覧は「管理者」かつ「スイッチで見える人」だけ。会員のIDは返さない', async () => {
  const origin2 = 'https://offline.example';
  const users = { o1: { ...owner }, a1: { ...admin }, u1: { id: 'u1', email: 'owner2@example.test', role: 'user', status: 'approved', authVersion: '1' } };
  const tokens = new Map([['a'.repeat(64), 'o1'], ['b'.repeat(64), 'a1'], ['c'.repeat(64), 'u1']]);
  const handler = createRaimoAuthGateway({ origin: origin2, member: async id => users[id] || null,
    sessions: { get: async t => tokens.has(t) ? { uid: tokens.get(t), authVersion: '1', expires: Date.now() + 60000 } : null, put: async () => {}, delete: async () => {} },
    authenticate: async () => null, allowLogin: async () => true, chatOwner: async () => null, forward: async () => ({}), attachmentSession: async () => ({}),
    featureFlags: async () => [{ feature: 'answer_feedback', stage: 'owner', owner_ids: ['owner@example.test', 'owner2@example.test'] }],
    listFeedback: async () => [{ user_id: 'secret-user', rating: 'bad', comment: 'c', question: 'q', answer: 'a', updated_at: 't' }] });
  const post = t => handler(new Request('https://g.example/admin/answer-feedback/list', { method: 'POST', headers: { Origin: origin2, Authorization: 'Bearer ' + t }, body: '{}' }));
  const ok = await post('a'.repeat(64));
  assert.equal(ok.status, 200);
  const body = await ok.json();
  assert.deepEqual(body, { feedback: [{ rating: 'bad', reasons: [], comment: 'c', question: 'q', answer: 'a', updated_at: 't', answer_mode: null, answer_tier: null, answer_model: null, answer_reused: null, sources: [] }], sources_top: [], source_clicks: 0 });
  assert.equal((await post('b'.repeat(64))).status, 404); // 管理者でも名指しが無い
  assert.equal((await post('c'.repeat(64))).status, 403); // 名指しでも一般会員
});

test('理由の選択肢: 超いいね・悪いねは決まった選択肢だけ複数選べる。いいねは理由なし', async () => {
  const base = { chat_id: 'c1', message_id: 'm2' };
  assert.deepEqual(parseFeedback({ ...base, rating: 'bad', reasons: ['vague', 'wrong', 'vague'] }).reasons, ['wrong', 'vague']);
  assert.deepEqual(parseFeedback({ ...base, rating: 'great' }).reasons, []);
  assert.throws(() => parseFeedback({ ...base, rating: 'great', reasons: ['wrong'] })); // 悪いねの理由は超いいねに付けられない
  assert.throws(() => parseFeedback({ ...base, rating: 'good', reasons: ['clear'] }));
  assert.throws(() => parseFeedback({ ...base, rating: 'bad', reasons: 'wrong' }));
  const s = setup();
  const r = await s.post('a'.repeat(64), { ...base, rating: 'bad', reasons: ['no_source'], comment: '物件の地域が違う' });
  assert.equal(r.status, 200);
  assert.deepEqual(s.saved[0].reasons, ['no_source']);
  assert.equal(s.saved[0].comment, '物件の地域が違う');
  assert.equal((await s.post('a'.repeat(64), { ...base, rating: 'bad', reasons: ['nope'] })).status, 400);
});

test('評価に答えの作り方を写す。引けない・失敗のときは列を足さずに保存する', async () => {
  const { answerHash, cleanMeta, feedbackMetaColumns } = await import('../lib/answerMeta.ts');
  assert.equal(await answerHash(' 回答本文 '), await answerHash('回答本文'));
  assert.equal(cleanMeta({ mode: 'x' }), null);
  assert.deepEqual(cleanMeta({ mode: 'semantic', tier: 'lite', model: 'gemini-2.5-flash-lite', reused: true }), { mode: 'semantic', tier: 'lite', model: 'gemini-2.5-flash-lite', reused: true });
  assert.equal(cleanMeta({ mode: 'normal', model: '<b>' }).model, '');
  assert.deepEqual(feedbackMetaColumns(null), {});
  const run = async answerMeta => {
    const saved = [], tokens = new Map([['a'.repeat(64), 'o1']]);
    const handler = createRaimoAuthGateway({ origin, member: async id => ({ o1: owner })[id] || null,
      sessions: { get: async t => tokens.has(t) ? { uid: tokens.get(t), authVersion: '1', expires: Date.now() + 60000 } : null, put: async () => {}, delete: async () => {} },
      authenticate: async () => null, allowLogin: async () => true, chatOwner: async () => 'o1',
      forward: async () => ({ session: {}, messages }), attachmentSession: async () => ({}),
      featureFlags: async () => [{ feature: 'answer_feedback', stage: 'owner', owner_ids: ['owner@example.test'] }],
      saveFeedback: async row => { saved.push(row); }, answerMeta });
    const r = await handler(new Request('https://g.example/answer-feedback', { method: 'POST', headers: { Origin: origin, Authorization: 'Bearer ' + 'a'.repeat(64) }, body: JSON.stringify({ chat_id: 'c1', message_id: 'm2', rating: 'bad', reasons: ['vague'] }) }));
    assert.equal(r.status, 200);
    return saved[0];
  };
  let seen;
  const row = await run(async (uid, chat, answer) => { seen = [uid, chat, answer]; return { mode: 'semantic', tier: 'lite', model: 'gemini-2.5-flash-lite', reused: true }; });
  assert.deepEqual(seen, ['o1', 'c1', '回答本文']);
  assert.deepEqual([row.answer_mode, row.answer_tier, row.answer_model, row.answer_reused], ['semantic', 'lite', 'gemini-2.5-flash-lite', true]);
  const none = await run(async () => null);
  assert.equal('answer_mode' in none, false);
  const broken = await run(async () => { throw new Error('missing table'); });
  assert.equal('answer_mode' in broken, false);
  assert.equal(broken.rating, 'bad');
});
