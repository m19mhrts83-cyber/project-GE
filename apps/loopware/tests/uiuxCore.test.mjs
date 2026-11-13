import { test } from 'node:test';
import assert from 'node:assert/strict';
import { loadLib } from './load.mjs';

const u = loadLib('uiuxCore');
const c = loadLib('decisionContract');
const plain = (x) => JSON.parse(JSON.stringify(x));

const raw = {
  id: '2026-11-14-home-order',
  title: 'ホームの並べ替え',
  app: 'dashboard',
  screen: 'ホーム',
  pr: 395,
  stage: 'plan',
  plans: [
    { id: 'A', label: '長押しで並べ替え', summary: 'iPhoneのホーム画面と同じ', image: 'storage:2026-11-14/A.png', points: ['先頭は固定'], applied: ['R800-001'] },
    { id: 'B', label: '編集ボタン', summary: '上の編集で↑↓', image: 'javascript:alert(1)' },
    { id: 'bad id!', label: 'x' },
  ],
  proposals: [{ id: 'P1', text: '最初の画面は判断が要るものだけ', why: '3回とも情報を減らした', concept: '情報の優先度', app: 'nope' }],
};

test('parseRound: 形を揃え、危ない画像と不正な id を落とす', () => {
  const r = u.parseRound(JSON.stringify(raw));
  assert.equal(r.plans.length, 2);
  assert.equal(r.plans[0].image, 'storage:2026-11-14/A.png');
  assert.equal(r.plans[1].image, undefined);
  assert.equal(r.pr, 395);
  assert.equal(r.app, 'dashboard');
  assert.equal(r.proposals[0].app, '*');
  assert.equal(u.parseRound({ id: 'x y', title: 't' }), null);
  assert.equal(u.cleanImage('storage:../secret.png'), undefined);
  assert.equal(u.cleanImage('https://example.com/a.png'), 'https://example.com/a.png');
});

test('pickComplete / pickAction: 選ぶ・どれも違う・全部迷う を分ける', () => {
  const r = u.parseRound(raw);
  assert.equal(u.pickComplete(r, { chosen: 'A', verdicts: {}, tags: {} }), true);
  assert.equal(u.pickComplete(r, { chosen: null, verdicts: { A: 'wrong' }, tags: {} }), false);
  const none = { chosen: null, verdicts: { A: 'wrong', B: 'hesitated' }, tags: {} };
  assert.equal(u.pickComplete(r, none), true);
  assert.equal(u.pickAction(r, none), 'reject');
  assert.equal(u.pickAction(r, { chosen: null, verdicts: { A: 'hesitated', B: 'hesitated' }, tags: {} }), 'hesitated');
  assert.equal(u.pickAction(r, { chosen: 'B', verdicts: {}, tags: {} }), 'adopt');
});

test('adoptedUiuxRules: 新しい判断が勝ち、取り消しは外す', () => {
  const rows = [
    { action: 'rule_accept', target_id: 'r1:P1', payload: { text: 'A', app: 'dashboard' }, decided_at: '2026-11-14T01:00:00Z' },
    { action: 'rule_accept', target_id: 'r1:P2', payload: { text: 'B' }, decided_at: '2026-11-14T01:00:00Z' },
    { action: 'rule_revert', target_id: 'r1:P2', payload: {}, decided_at: '2026-11-14T02:00:00Z' },
    { action: 'rule_once', target_id: 'r1:P3', payload: { text: 'C' }, decided_at: '2026-11-14T01:00:00Z' },
  ];
  const got = plain(u.adoptedUiuxRules(rows));
  assert.deepEqual(got.map((r) => r.key), ['r1:P1']);
  assert.equal(got[0].app, 'dashboard');
  assert.deepEqual(plain(u.decidedProposals(rows, 'r1')), { P1: 'rule_accept', P2: 'rule_revert', P3: 'rule_once' });
});

test('契約: uiux の surface と理由タグがある', () => {
  for (const s of ['uiux_plan', 'uiux_fix', 'uiux_rule']) assert.ok(c.SURFACES.includes(s));
  assert.ok('phone' in c.UIUX_PLAN_REASON_TAGS);
  assert.ok('app_only' in c.UIUX_RULE_REASON_TAGS);
});
