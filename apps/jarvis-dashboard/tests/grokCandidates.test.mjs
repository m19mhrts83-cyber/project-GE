import { test } from 'node:test';
import assert from 'node:assert/strict';
import { buildViews, countByState, normName, parseSnapshot, stateFromLedgerStatus } from '../lib/grokCandidates.ts';

const cand = (name, extra = {}) => ({ n: 1, name, area: '緑区', ch: 'web_form', dt: '2026-11-25', ...extra });
const item = (kind, name, extra = {}) => ({ key: normName(name), kind, why: '', seen_at: '2026-11-25T03:00:00+00:00', md: 'x.md', cand: cand(name), ...extra });
const led = (name, status, source = 's9_candidates_2026-11-25') => ({ name, status, source });

test('会社形態・空白・括弧を除いて同じ会社と見る', () => {
  assert.equal(normName('株式会社 架空・不動産（本店）'), normName('架空不動産本店'));
});

test('台帳の status を状態に写す', () => {
  assert.equal(stateFromLedgerStatus('pending'), 'pending');
  assert.equal(stateFromLedgerStatus('contacted'), 'sent');
  assert.equal(stateFromLedgerStatus('replied'), 'sent');
  assert.equal(stateFromLedgerStatus('skip'), 'skipped');
  assert.equal(stateFromLedgerStatus(null), 'pending');
});

test('追加済みは台帳の最新の状態（送信済みなど）を見る。台帳に無ければ送信待ち', () => {
  const v = buildViews([item('add', '架空A'), item('add', '架空B')], [led('架空A', 'contacted')]);
  assert.equal(v.find((x) => x.name === '架空A').state, 'sent');
  assert.equal(v.find((x) => x.name === '架空B').state, 'pending');
});

test('重複は理由と、相手の台帳での状態を付ける', () => {
  const v = buildViews(
    [item('dup', '架空C', { why: '台帳に既存（架空C社・contacted）', existing: { name: '架空C社', status: 'pending' } })],
    [led('架空C社', 'contacted', 'manual')],
  );
  assert.equal(v[0].state, 'dup');
  assert.match(v[0].reason, /台帳に既存/);
  assert.match(v[0].reason, /台帳では送信済み/);
  assert.equal(v[0].canDecide, false);
});

test('判断待ちだけ採用ボタンが出る。受付済み・台帳入りは出ない', () => {
  const items = [item('consult', '架空D'), item('consult', '架空E'), item('consult', '架空F')];
  const v = buildViews(items, [led('架空F', 'pending', 's9_slack_2026-11-25')], [{ name: '架空E', decision: 'adopt' }]);
  const by = (n) => v.find((x) => x.name === n);
  assert.equal(by('架空D').state, 'decide');
  assert.equal(by('架空D').canDecide, true);
  assert.equal(by('架空E').state, 'queued');
  assert.equal(by('架空E').canDecide, false);
  assert.equal(by('架空F').state, 'pending');
  assert.equal(by('架空F').canDecide, false);
});

test('見送りで台帳に入った判断待ちは見送り', () => {
  const v = buildViews([item('consult', '架空G')], [led('架空G', 'skip', 's9_slack_2026-11-25')]);
  assert.equal(v[0].state, 'skipped');
});

test('送らない候補', () => {
  const v = buildViews([item('drop', '架空H', { why: 'メール／フォームが見つからない' })], []);
  assert.equal(v[0].state, 'drop');
  assert.match(v[0].reason, /見つからない/);
});

test('写しが無い取り込み分は台帳の出どころ印から補う（ボタンなし・手入力の行は出さない）', () => {
  const v = buildViews([], [led('架空I', 'pending'), led('架空J', 'pending', 'manual_2026')]);
  assert.deepEqual(v.map((x) => x.name), ['架空I']);
  assert.equal(v[0].fromLedgerOnly, true);
  assert.equal(v[0].canDecide, false);
});

test('今見るべき順（判断待ち→送信待ち→送信済み→重複）に並ぶ', () => {
  const v = buildViews(
    [item('dup', '架空K', { existing: { name: '架空K', status: 'pending' } }), item('consult', '架空L'), item('add', '架空M')],
    [led('架空M', 'pending')],
  );
  assert.deepEqual(v.map((x) => x.state), ['decide', 'pending', 'dup']);
  assert.equal(countByState(v).decide, 1);
});

test('壊れた写し・空は null、不正な行は読み飛ばす', () => {
  assert.equal(parseSnapshot(undefined), null);
  assert.equal(parseSnapshot('{'), null);
  assert.equal(parseSnapshot('{"items":1}'), null);
  const p = parseSnapshot(JSON.stringify({ generated_at: 'x', items: [{ key: 'a', kind: 'zzz', cand: { name: 'n' } }, item('add', '架空N')] }));
  assert.equal(p.items.length, 1);
});
