import { test } from 'node:test';
import assert from 'node:assert/strict';
import { loadLib } from './load.mjs';

const s = loadLib('slidesCore');
const c = loadLib('decisionContract');
const plain = (x) => JSON.parse(JSON.stringify(x));

const raw = {
  id: '2026-11-dx-gojokai',
  title: '11月 DX互助会',
  stage: 'plan',
  plans: [
    { id: 'A', label: '事例中心', summary: 'メンバー事例を3つ', outline: ['活動概要', '事例'], applied: ['2026-10-dx:P1'] },
    { id: 'B', label: '新技術中心', summary: 'ループウェア紹介' },
    { id: 'bad id!', label: 'x' },
  ],
  proposals: [{ id: 'P1', text: '専門用語は言い換えを添える', why: '4か所で言い換えた', concept: '用語' }],
};

test('デッキを読み、壊れた案は落とし、観点が無ければ既定を使う', () => {
  const d = s.parseDeck(JSON.stringify(raw));
  assert.equal(d.id, '2026-11-dx-gojokai');
  assert.deepEqual(plain(d.plans.map((p) => p.id)), ['A', 'B']);
  assert.equal(d.axes.length, s.DEFAULT_AXES.length);
  assert.equal(d.proposals[0].concept, '用語');
  assert.equal(s.parseDeck('{壊れた'), null);
  assert.equal(s.parseDeck({ id: 'x y', title: 't' }), null);
});

test('作る前は 案1つ＋全観点 が揃うまで送れない', () => {
  const d = s.parseDeck(raw);
  const all = Object.fromEntries(d.axes.map((a) => [a.key, 0]));
  assert.equal(s.planComplete(d, { plan: null, axes: all }), false);
  assert.equal(s.planComplete(d, { plan: 'A', axes: {} }), false);
  assert.equal(s.planComplete(d, { plan: 'A', axes: all }), true);
  assert.equal(s.planComplete(d, { plan: 'A', axes: { ...all, volume: 9 } }), false);
});

test('資料の基準は「いちばん新しい判断が採用」のものだけ。取り消し・違うに変えたら外れる', () => {
  const rows = [
    { action: 'rule_accept', target_id: 'd1:P1', payload: { deck_id: 'd1', text: '用語は言い換える' }, decided_at: '2026-11-01T00:00:00Z' },
    { action: 'rule_accept', target_id: 'd1:P2', payload: { deck_id: 'd1', text: '事例は3行' }, decided_at: '2026-11-01T00:00:00Z' },
    { action: 'rule_revert', target_id: 'd1:P2', payload: {}, decided_at: '2026-11-02T00:00:00Z' },
    { action: 'rule_once', target_id: 'd1:P3', payload: { text: '今回だけ' }, decided_at: '2026-11-01T00:00:00Z' },
    { action: 'rule_reject', target_id: 'd1:P4', payload: { text: 'x' }, decided_at: '2026-11-01T00:00:00Z' },
    { action: 'rule_accept', target_id: 'd1:P4', payload: { text: '採り直した' }, decided_at: '2026-11-03T00:00:00Z' },
  ];
  const got = s.adoptedSlideRules(rows);
  assert.deepEqual(plain(got.map((r) => r.key)), ['d1:P4', 'd1:P1']);
  assert.deepEqual(plain(s.decidedProposals(rows, 'd1')), { P1: 'rule_accept', P2: 'rule_revert', P3: 'rule_once', P4: 'rule_accept' });
});

test('資料の判断は契約に通る（surface と理由タグ）', () => {
  const n = c.normalizeDecision({ surface: 'slide_rule', action: 'rule_once', source: 'loopware', targetType: 'slide_proposal', targetId: 'd1:P1', reasonTags: ['by_chance'], idemKey: 'slide-1' });
  assert.equal(n.ok, true);
  assert.deepEqual(plain(n.row.payload.reason_tags), ['by_chance']);
  assert.equal(n.row.payload.outcome, 'later');
  const p = c.normalizeDecision({ surface: 'slide_plan', action: 'adopt', source: 'loopware', targetType: 'slide_deck', targetId: 'd1', reasonTags: ['off_theme'], idemKey: 'slide-2' });
  assert.equal(p.ok, true);
  assert.deepEqual(plain(p.row.payload.reason_tags), ['off_theme']);
  assert.equal(c.normalizeDecision({ surface: 'slide_fix', action: 'comment', source: 'script', targetType: 'slide_deck', targetId: 'd1', aiProposal: 'あ', finalText: 'い', idemKey: 'slide-3' }).row.edited, true);
});
