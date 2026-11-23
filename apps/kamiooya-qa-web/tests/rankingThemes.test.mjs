import test from 'node:test';
import assert from 'node:assert/strict';
import { parseThemeDecision, shapeRound, rebuildState, REBUILD_DAILY_LIMIT } from '../lib/rankingThemes.ts';
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

test('検討案として採用を選べ、どの判断も理由が要る（2026-11-23）', () => {
  assert.equal(parseThemeDecision({ round_id: 'r20261116', theme_id: 't1', choice: 'consider', reason: '次回もう少し具体的に' }).choice, 'consider');
  for (const choice of ['adopt', 'consider', 'reject']) {
    assert.throws(() => parseThemeDecision({ round_id: 'r20261116', theme_id: 't1', choice, reason: '  ' }), e => e.code === 'reason_required');
  }
  assert.throws(() => parseThemeDecision({ round_id: 'r20261116', theme_id: 't1', choice: 'revise', revised_title: '題' }), e => e.code === 'reason_required');
  const s = shapeRound({ ...round, themes: [{ id: 't1', title: 'A', follows: '修繕見積もりの読み方' }] }, []);
  assert.equal(s.themes[0].follows, '修繕見積もりの読み方');
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

test('作り直しの状態: 作成中・作れなかった可能性・1日の上限', () => {
  const now = Date.parse('2026-11-23T10:00:00Z');
  const at = m => new Date(now - m * 60000).toISOString();
  assert.equal(rebuildState([], '2026-11-17T00:00:00Z', now).state, 'idle');
  const running = rebuildState([{ requested_by: 'o1', requested_at: at(5), dispatched: true }], '2026-11-17T00:00:00Z', now);
  assert.equal(running.state, 'running');
  assert.equal(running.last_requested_by, 'o1');
  // 新しい回ができたら作成中は終わり
  assert.equal(rebuildState([{ requested_at: at(5), dispatched: true }], at(1), now).state, 'idle');
  // 40分たっても回ができない時は、もう一度押せて「作れなかった可能性」を出す
  const stale = rebuildState([{ requested_at: at(50), dispatched: true }], '2026-11-17T00:00:00Z', now);
  assert.equal(stale.state, 'idle'); assert.equal(stale.maybe_failed, true);
  // 起動できなかった依頼は数えない
  assert.equal(rebuildState([{ requested_at: at(5), dispatched: false }], '2026-11-17T00:00:00Z', now).state, 'idle');
  const many = Array.from({ length: REBUILD_DAILY_LIMIT }, (_, i) => ({ requested_at: at(60 + i * 60), dispatched: true }));
  assert.equal(rebuildState(many, at(1), now).state, 'limit');
});

test('作り直しは管理者だけ、作成中は重ねて起動しない、鍵がなければ起動しない', async () => {
  const origin = 'https://offline.example';
  const members = { o1: { id: 'o1', email: 'owner@example.test', role: 'admin', status: 'approved', authVersion: '1', name: '松野' },
    u1: { id: 'u1', email: 'user@example.test', role: 'user', status: 'approved', authVersion: '1' } };
  const sessions = new Map([['a'.repeat(64), { uid: 'o1', authVersion: '1', expires: Date.now() + 60000 }], ['c'.repeat(64), { uid: 'u1', authVersion: '1', expires: Date.now() + 60000 }]]);
  const reqs = []; let configured = false; let dispatched = 0;
  const handler = createRaimoAuthGateway({ origin, member: async id => members[id] || null,
    sessions: { get: async t => sessions.get(t) || null, put: async () => {}, delete: async () => {} },
    authenticate: async () => null, allowLogin: async () => true, chatOwner: async () => null,
    forward: async () => { throw new Error('should not forward'); }, attachmentSession: async () => ({}),
    featureFlags: async () => [{ feature: 'ranking_themes', stage: 'all', owner_ids: [], reviewer_ids: [] }],
    themeRounds: async () => [round], themeDecisions: async () => [], saveThemeDecision: async () => {},
    rebuildRequests: async () => [...reqs].reverse(),
    requestRankingRebuild: async uid => { if (!configured) return { ok: false, error: 'not_configured' }; dispatched++; reqs.push({ requested_by: uid, requested_at: new Date().toISOString(), dispatched: true }); return { ok: true }; } });
  const post = (t, p) => handler(new Request('https://g.example' + p, { method: 'POST', headers: { Origin: origin, Authorization: 'Bearer ' + t, 'Content-Type': 'application/json' }, body: '{}' }));
  assert.notEqual((await post('c'.repeat(64), '/admin/ranking-themes/rebuild')).status, 200);
  const nokey = await post('a'.repeat(64), '/admin/ranking-themes/rebuild');
  assert.equal(nokey.status, 503); assert.equal((await nokey.json()).error, 'not_configured');
  configured = true;
  const ok = await (await post('a'.repeat(64), '/admin/ranking-themes/rebuild')).json();
  assert.equal(ok.ok, true); assert.equal(ok.rebuild.state, 'running'); assert.equal(ok.rebuild.last_requested_by_name, '松野');
  assert.equal(JSON.stringify(ok).includes('o1'), false);
  assert.equal((await post('a'.repeat(64), '/admin/ranking-themes/rebuild')).status, 409);
  assert.equal(dispatched, 1);
  const list = await (await post('a'.repeat(64), '/admin/ranking-themes/list')).json();
  assert.equal(list.rebuild.state, 'running');
});
