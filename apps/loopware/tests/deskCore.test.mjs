import { test } from 'node:test';
import assert from 'node:assert/strict';
import { loadLib } from './load.mjs';

const d = loadLib('deskCore');
const plain = (x) => JSON.parse(JSON.stringify(x));

test('行をカードにする（本文は引用の前まで・ルール番号をまとめる）', () => {
  const c = d.toCard({
    id: 'gha-cw-7790cf4', subject: 'エアコン', partner: 'ミニテック', from_email: 'a@x.jp', lane: 'partner',
    original_body: '松野様\nお世話になります。\n\n> 前のメール\n> 引用',
    draft_text: 'ミニテック様\n\n確認します。',
    payload: { slack_ma_digest: { score: 88, summary: '修理日程' }, slack_ma_posted_at: 't', applied_rules: ['R116-002'], draft_rules: ['R211-001', 'R116-002'] },
  });
  assert.equal(c.summary, '修理日程');
  assert.equal(c.score, 88);
  assert.deepEqual(plain(c.bodyLines), ['松野様', 'お世話になります。', '']);
  assert.deepEqual(plain(c.draftLines), ['ミニテック様', '', '確認します。']);
  assert.deepEqual(plain(c.appliedRules), ['R116-002', 'R211-001']);
  assert.equal(c.postedToSlack, true);
});

test('並び: 迷ったものは後ろ・Slack に出したもの・点数・新しい順', () => {
  const mk = (id, o) => ({ ...d.toCard({ id, received_at: o.at || '2026-11-08T00:00:00Z', payload: o.pl || {} }) });
  const cards = [
    mk('aaaaaa1', { pl: { loopware_hesitated_at: 'x', slack_ma_posted_at: 't', slack_ma_digest: { score: 999 } } }),
    mk('aaaaaa2', { pl: {} , at: '2026-11-08T05:00:00Z' }),
    mk('aaaaaa3', { pl: { slack_ma_posted_at: 't', slack_ma_digest: { score: 10 } } }),
    mk('aaaaaa4', { pl: { slack_ma_posted_at: 't', slack_ma_digest: { score: 50 } } }),
    mk('aaaaaa5', { pl: {}, at: '2026-11-08T06:00:00Z' }),
  ];
  assert.deepEqual(plain(d.orderCards(cards).map((c) => c.id)), ['aaaaaa4', 'aaaaaa3', 'aaaaaa5', 'aaaaaa2', 'aaaaaa1']);
});

test('デスクに出す行・ボタンの対応', () => {
  assert.equal(d.isDeskRow({ id: 'abc-123456', status: 'pending', lane: 'partner' }), true);
  assert.equal(d.isDeskRow({ id: 're-vendor-123456', status: 'pending' }), false);
  assert.equal(d.isDeskRow({ id: 'abc-123456', status: 'sent' }), false);
  assert.equal(d.isDeskRow({ id: 'abc-123456', status: 'pending', lane: 'openchat' }), false);
  assert.equal(d.isDeskRow({ id: 'x', status: 'pending' }), false);
  assert.equal(d.CHOICE_ACTION.hesitate, 'hesitated');
  assert.equal(d.CHOICE_MA.hesitate, undefined);
  assert.equal(d.CHOICE_MA.todo, 'todoist');
});

test('経過の表示', () => {
  const now = new Date('2026-11-08T12:00:00Z');
  assert.equal(d.agoLabel('2026-11-08T11:30:00Z', now), '30分前');
  assert.equal(d.agoLabel('2026-11-08T07:00:00Z', now), '5時間前');
  assert.equal(d.agoLabel('2026-11-05T12:00:00Z', now), '3日前');
  assert.equal(d.agoLabel(null, now), '');
});
