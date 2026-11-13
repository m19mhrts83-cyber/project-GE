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

test('残り案件と次の一手（型で決める）', () => {
  const now = new Date('2026-11-08T12:00:00Z');
  const mk = (o) => ({ ...d.toCard({ id: 'abc-123456', lane: o.lane || 'general', received_at: o.at, draft_text: o.draft || '', payload: o.pl || {} }) });
  assert.equal(d.isLeftover(mk({ at: '2026-11-08T10:00:00Z' }), now), false);
  assert.equal(d.isLeftover(mk({ at: '2026-11-07T10:00:00Z' }), now), true);
  assert.equal(d.isLeftover(mk({ at: '2026-11-08T11:00:00Z', pl: { loopware_hesitated_at: 'x' } }), now), true);
  assert.equal(d.nextStepFor(mk({ at: '2026-11-08T11:00:00Z', pl: { loopware_stay_reason: 'waiting' } }), now).effect, 'snooze3');
  assert.equal(d.nextStepFor(mk({ at: '2026-11-08T11:00:00Z', pl: { loopware_stay_reason: 'no_time' } }), now).effect, 'todo');
  assert.equal(d.nextStepFor(mk({ at: '2026-11-08T11:00:00Z', draft: 'x', pl: { loopware_stay_reason: 'need_info' } }), now).id, 'needinfo_reply');
  assert.equal(d.nextStepFor(mk({ at: '2026-11-04T11:00:00Z' }), now).id, 'old_low_skip');
  assert.equal(d.nextStepFor(mk({ at: '2026-11-07T11:00:00Z', lane: 'partner', draft: '下書き' }), now).id, 'draft_reply');
  assert.equal(d.nextStepFor(mk({ at: '2026-11-07T11:00:00Z' }), now).id, 'default_todo');
});

test('人が判断するカードだけデスクに出す（自動のお知らせ・メルマガはまとめ側）', () => {
  const row = (o) => ({ id: 'gha-abc1234', status: 'pending', lane: 'general', kind: 'mail', ...o });
  // 自動のお知らせ・広告・認証コード
  assert.equal(d.isDeskRow(row({ from_email: 'post_master@netbk.co.jp', subject: '振込入金のお知らせ', original_body: 'いつもご利用' })), false);
  assert.equal(d.isDeskRow(row({ from_email: 'mail-info@diamond.co.jp', subject: '記事', original_body: '松野様\n配信停止はこちら' })), false);
  assert.equal(d.isDeskRow(row({ kind: 'skim', from_email: 'a.b@x.jp', subject: 'RE: 件' })), false);
  // 支払いの失敗は自動でも出す
  assert.equal(d.isDeskRow(row({ from_email: 'smbc_service@dn.smbc.co.jp', subject: '【三井住友銀行】口座引き落とし未済のお知らせ' })), true);
  assert.equal(d.isDeskRow(row({ kind: 'skim', from_email: 'statement@vpass.ne.jp', subject: 'カードがご利用いただけませんでした【三井住友カード】' })), true);
  // 人が書いたメール
  assert.equal(d.isDeskRow(row({ from_email: 'to-sirai@nakado.com', subject: '富士見台物件について', original_body: '松野様\nお世話になります。' })), true);
  assert.equal(d.isDeskRow(row({ from_email: 'someone@gmail.com', subject: 'こんにちは' })), true);
  assert.equal(d.isDeskRow(row({ from_email: 'info@shop.jp', subject: 'Re: お見積り' })), true);
  // パートナー・Slack に出した・迷ったは従来どおり出す
  assert.equal(d.isDeskRow(row({ lane: 'partner', from_email: 'info@x.jp', subject: 'お知らせ' })), true);
  assert.equal(d.isDeskRow(row({ from_email: 'info@x.jp', subject: 'お知らせ', payload: { slack_ma_posted_at: 't' } })), true);
  assert.equal(d.isDeskRow(row({ kind: 'skim', from_email: 'info@x.jp', payload: { loopware_hesitated_at: 't' } })), true);
});

test('フリーメールからの転送は、転送元の配信停止の文言があっても出す', () => {
  const r = { id: 'gha-abc1235', status: 'pending', lane: 'general', kind: 'mail', from_email: 'family.x@gmail.com',
    subject: 'Fwd: 【資生堂オンラインストア】お支払いについて', original_body: '---------- Forwarded message ---------\n配信停止はこちら' };
  assert.equal(d.isDeskRow(r), true);
});

test('見落としの判断は業者返信の id も受ける（デスクには出さない）', () => {
  assert.equal(d.isDeskItemId('re-vendor-067c20c0e7fc1a27'), false);
  assert.equal(d.isTriageItemId('re-vendor-067c20c0e7fc1a27'), true);
  assert.equal(d.isVendorItemId('re-vendor-067c20c0e7fc1a27'), true);
  assert.equal(d.isTriageItemId('gha-cw-7790cf4'), true);
  assert.equal(d.isTriageItemId('bad id!'), false);
});

test('1つ前のやりとり: payload.thread_context をカードに載せる（自分が送ったものに印）', () => {
  const c = d.toCard({
    id: 'gha-aaaaaa1', gmail_thread_id: 'T1',
    payload: { thread_context: [
      { at: '2026/11/12 21:39', mine: true, subject: 'お礼', body: '山本様\nご注文ありがとうございます' },
      { at: 'x', mine: false, subject: '', body: '   ' },
    ] },
  });
  assert.equal(c.threadId, 'T1');
  assert.equal(c.thread.length, 1);
  assert.equal(c.thread[0].mine, true);
  assert.deepEqual(plain(d.toCard({ id: 'bbbbbb1' }).thread), []);
});

test('返信済み・見送り済みの印: 同じスレッド → 同じ相手。双子と自分は数えない', () => {
  const card = { id: 'gha-p-aaaaaa1', fromEmail: 'Yamamoto@x.jp', threadId: 'T1' };
  const decided = [
    { id: 'aaaaaa1', status: 'skipped', from_email: 'yamamoto@x.jp', gmail_thread_id: 'T1', updated_at: '2026-11-12T20:00:00Z' }, // 双子
    { id: 'old0001', status: 'sent', from_email: 'yamamoto@x.jp', gmail_thread_id: 'T1', updated_at: '2026-11-10T03:00:00Z' },
    { id: 'old0002', status: 'skipped', from_email: 'yamamoto@x.jp', gmail_thread_id: 'T9', updated_at: '2026-11-12T00:00:00Z' },
    { id: 'old0003', status: 'skipped', from_email: 'yamamoto@x.jp', gmail_thread_id: 'T8', updated_at: '2026-11-11T00:00:00Z' },
    { id: 'old0004', status: 'pending', from_email: 'yamamoto@x.jp', updated_at: '2026-11-12T00:00:00Z' },
    { id: 'other01', status: 'done', from_email: 'z@y.jp', updated_at: '2026-11-12T00:00:00Z' },
  ];
  const notes = d.historyNotes(card, decided);
  assert.deepEqual(plain(notes), [
    '同じスレッドで 11/10 に返信済み',
    'この相手の過去30日: 返信 1・見送り 2（直近は 11/12 見送り）',
  ]);
  assert.deepEqual(plain(d.historyNotes({ id: 'zzzzzz1', fromEmail: '', threadId: '' }, decided)), []);
});

test('いまの状態の一行', () => {
  assert.equal(d.stateLine({ postedToSlack: true, hesitatedAt: null, history: [] }), 'Slack に出ましたが、まだ返信も見送りもしていません');
  assert.equal(d.stateLine({ postedToSlack: false, hesitatedAt: 'x', history: [] }), '迷って残っています');
  assert.equal(d.stateLine({ postedToSlack: false, hesitatedAt: null, history: [] }), 'まだ判断していません');
});
