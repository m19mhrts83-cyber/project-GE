import test from 'node:test';
import assert from 'node:assert/strict';
import { parseThemeDecision, shapeRound } from '../lib/rankingThemes.ts';
import { createRaimoAuthGateway } from '../lib/raimoAuthGateway.ts';

const round = { id: 'r20261116', created_at: '2026-11-16T00:00:00Z', period_days: 120, model: 'gemini',
  ranking: [{ topic: '修繕の見積もり', count: 40, chatbot: 2, forum: 8, openchat: 30, examples: ['a', 'b', 'c', 'd'], author_name: 'X' }],
  themes: [{ id: 't1', title: '修繕見積もりの読み方', why: 'w', evidence: 'e', format: '60分', target: '初心者' }, { id: 't2', title: 'B' }],
  stats: { chatbot: 88, forum: 100, openchat: 900, courses: 274 } };

test('判断の入力は決まった形だけ通す', () => {
  assert.deepEqual(parseThemeDecision({ round_id: 'r20261116', theme_id: 't1', choice: 'adopt', reason: ' 良い ', revised_title: 'x' }),
    { round_id: 'r20261116', theme_id: 't1', choice: 'adopt', revised_title: '', reason: '良い' });
  assert.throws(() => parseThemeDecision({ round_id: 'r20261116', theme_id: 't1', choice: 'revise' }), e => e.code === 'invalid_request');
  assert.throws(() => parseThemeDecision({ round_id: 'x', theme_id: 't1', choice: 'adopt' }));
  assert.throws(() => parseThemeDecision({ round_id: 'r20261116', theme_id: 't1', choice: 'maybe' }));
  assert.throws(() => parseThemeDecision({ round_id: 'r20261116', theme_id: 't1', choice: 'reject', reason: 'x'.repeat(1001) }));
});

test('画面に返すのは決まった項目だけで、判断が付く', () => {
  const s = shapeRound(round, [{ round_id: 'r20261116', theme_id: 't2', choice: 'reject', reason: '既にある', revised_title: '' }]);
  assert.equal(s.ranking[0].examples.length, 3);
  assert.equal(JSON.stringify(s).includes('author_name'), false);
  assert.equal(s.themes[0].decision, null);
  assert.equal(s.themes[1].decision.choice, 'reject');
});

test('スイッチで見える管理者だけが一覧と判断を使える', async () => {
  const origin = 'https://offline.example';
  const members = { o1: { id: 'o1', email: 'owner@example.test', role: 'master_admin', status: 'approved', authVersion: '1' },
    a1: { id: 'a1', email: 'admin@example.test', role: 'admin', status: 'approved', authVersion: '1' } };
  const sessions = new Map([['a'.repeat(64), { uid: 'o1', authVersion: '1', expires: Date.now() + 60000 }], ['b'.repeat(64), { uid: 'a1', authVersion: '1', expires: Date.now() + 60000 }]]);
  const saved = [];
  const handler = createRaimoAuthGateway({ origin, member: async id => members[id] || null,
    sessions: { get: async t => sessions.get(t) || null, put: async () => {}, delete: async () => {} },
    authenticate: async () => null, allowLogin: async () => true, chatOwner: async () => null,
    forward: async () => { throw new Error('should not forward'); }, attachmentSession: async () => ({}),
    featureFlags: async () => [{ feature: 'ranking_themes', stage: 'owner', owner_ids: ['o1'], reviewer_ids: [] }],
    themeRounds: async () => [round], themeDecisions: async () => saved, saveThemeDecision: async r => { saved.push(r); } });
  const post = (t, p, body) => handler(new Request('https://g.example' + p, { method: 'POST', headers: { Origin: origin, Authorization: 'Bearer ' + t, 'Content-Type': 'application/json' }, body: JSON.stringify(body) }));
  assert.equal((await post('b'.repeat(64), '/admin/ranking-themes/list', {})).status, 404);
  const ok = await (await post('a'.repeat(64), '/admin/ranking-themes/list', {})).json();
  assert.equal(ok.latest.themes.length, 2);
  assert.equal((await post('a'.repeat(64), '/admin/ranking-themes/decide', { round_id: 'r20261116', theme_id: 't9', choice: 'adopt' })).status, 400);
  assert.equal((await post('a'.repeat(64), '/admin/ranking-themes/decide', { round_id: 'r20261116', theme_id: 't1', choice: 'revise', revised_title: '見積もりの比べ方', reason: '題を具体的に' })).status, 200);
  assert.equal(saved[0].decided_by, 'o1');
  const after = await (await post('a'.repeat(64), '/admin/ranking-themes/list', {})).json();
  assert.equal(after.latest.themes[0].decision.revised_title, '見積もりの比べ方');
});
