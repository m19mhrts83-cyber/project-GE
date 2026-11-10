import test from 'node:test';
import assert from 'node:assert/strict';
import { createRaimoAuthGateway } from '../lib/raimoAuthGateway.ts';
import { parseSourceClick, summarizeSourceClicks } from '../lib/sourceClicks.ts';

const origin = 'https://offline.example';
const owner = { id: 'o1', email: 'owner@example.test', role: 'master_admin', status: 'approved', authVersion: '1' };
const admin = { id: 'a1', email: 'admin@example.test', role: 'admin', status: 'approved', authVersion: '1' };
const messages = [{ id: 'm1', role: 'user', content: '火災保険 保険料' }, { id: 'm2', role: 'assistant', content: '回答本文' }];
const tokens = new Map([['a'.repeat(64), 'o1'], ['b'.repeat(64), 'a1']]);
function gateway(extra = {}, stage = 'owner') {
  return createRaimoAuthGateway({ origin, member: async id => ({ o1: owner, a1: admin })[id] || null,
    sessions: { get: async t => tokens.has(t) ? { uid: tokens.get(t), authVersion: '1', expires: Date.now() + 60000 } : null, put: async () => {}, delete: async () => {} },
    authenticate: async () => null, allowLogin: async () => true,
    chatOwner: async id => id === 'c1' ? 'o1' : id === 'c2' ? 'a1' : 'x',
    forward: async (method, path) => ({ session: {}, messages: path.endsWith('/c1') || path.endsWith('/c2') ? messages : [] }),
    attachmentSession: async () => ({}),
    featureFlags: async () => [{ feature: 'answer_feedback', stage, owner_ids: ['owner@example.test'], reviewer_ids: [] }],
    ...extra });
}
const req = (path, t, body) => new Request('https://g.example' + path, { method: 'POST', headers: { Origin: origin, Authorization: 'Bearer ' + t }, body: JSON.stringify(body) });
const click = { chat_id: 'c1', message_id: 'm2', kind: 'comment', source_key: '12345', title: ' コミュニティ投稿 #12345\n（2026年10月） ', label: 'コミュニティ1', action: 'open_text' };

test('根拠を開いた記録: 対象者だけ保存。質問はサーバーがチャットから引く', async () => {
  const saved = [];
  const h = gateway({ saveSourceClick: async row => { saved.push(row); } });
  const r = await h(req('/answer-source-click', 'a'.repeat(64), { ...click, user_id: 'other', question: '偽' }));
  assert.equal(r.status, 200);
  assert.deepEqual({ ...saved[0], clicked_at: 'x' }, { user_id: 'o1', chat_id: 'c1', message_id: 'm2', kind: 'comment', source_key: '12345',
    title: 'コミュニティ投稿 #12345 （2026年10月）', label: 'コミュニティ1', action: 'open_text', question: '火災保険 保険料', clicked_at: 'x' });
  assert.equal((await h(req('/answer-source-click', 'b'.repeat(64), { ...click, chat_id: 'c2' }))).status, 404); // スイッチで見えない
  assert.equal((await h(req('/answer-source-click', 'a'.repeat(64), { ...click, chat_id: 'c3' }))).status, 403); // 他人のチャット
  assert.equal((await h(req('/answer-source-click', 'a'.repeat(64), { ...click, message_id: 'm1' }))).status, 404); // 質問側
  assert.equal((await h(req('/answer-source-click', 'a'.repeat(64), { ...click, kind: 'web' }))).status, 400);
  assert.equal(saved.length, 1);
  const off = gateway({ saveSourceClick: async row => { saved.push(row); } }, 'off');
  assert.equal((await off(req('/answer-source-click', 'a'.repeat(64), click))).status, 404);
});

test('入力の検査', () => {
  assert.throws(() => parseSourceClick({ ...click, action: 'hover' }));
  assert.throws(() => parseSourceClick({ ...click, source_key: '' }));
  assert.throws(() => parseSourceClick({ ...click, source_key: 'x'.repeat(301) }));
  assert.equal(parseSourceClick({ ...click, title: '' }).title, '12345');
  assert.equal(parseSourceClick({ ...click, title: 'あ'.repeat(400) }).title.length, 300);
});

test('一覧: 評価に「開いた根拠」が付き、よく参考にされた根拠が人数順に出る。会員IDは出さない', async () => {
  const clicks = [
    { user_id: 'u1', chat_id: 'c1', message_id: 'm2', kind: 'video_chunk', source_key: 'v1', title: '融資セミナー ・ 12:30', label: 'セミナー1' },
    { user_id: 'u1', chat_id: 'c1', message_id: 'm2', kind: 'comment', source_key: '9', title: 'コミュニティ投稿 #9', label: '' },
    { user_id: 'u2', chat_id: 'c9', message_id: 'm7', kind: 'video_chunk', source_key: 'v1', title: '融資セミナー ・ 12:30', label: 'セミナー2' },
  ];
  const h = gateway({ listFeedback: async () => [{ user_id: 'u1', chat_id: 'c1', message_id: 'm2', rating: 'great', reasons: ['source'], comment: '', question: 'q', answer: 'a', updated_at: 't' }],
    listSourceClicks: async () => clicks });
  const body = await (await h(req('/admin/answer-feedback/list', 'a'.repeat(64), {}))).json();
  assert.deepEqual(body.feedback[0].sources, [{ kind: 'video_chunk', title: '融資セミナー ・ 12:30', label: 'セミナー1' }, { kind: 'comment', title: 'コミュニティ投稿 #9', label: '' }]);
  assert.deepEqual(body.sources_top[0], { kind: 'video_chunk', title: '融資セミナー ・ 12:30', people: 2, answers: 2 });
  assert.equal(body.source_clicks, 3);
  assert.ok(!JSON.stringify(body).includes('u1') && !JSON.stringify(body).includes('u2'));
  // 記録が読めなくても評価の一覧は出る
  const broken = gateway({ listFeedback: async () => [], listSourceClicks: async () => { throw new Error('x'); } });
  assert.equal((await broken(req('/admin/answer-feedback/list', 'a'.repeat(64), {}))).status, 200);
  assert.equal(summarizeSourceClicks([]).top.length, 0);
});
