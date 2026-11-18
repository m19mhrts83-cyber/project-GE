// 23番オプチャ（成果達成者限定）を見てよい人だけに出す（2026-11-18）。
import test from 'node:test';
import assert from 'node:assert/strict';
import { filterOpenchatRows, hiddenOpenchats, isRestrictedOpenchat, needsViewer, viewerFromToken } from '../lib/openchatAccess.ts';
import { issueSession } from '../supabase/functions/community-attachments/index.ts';

const owner = { id: 'u-owner', email: 'owner@example.test' };
const member = { id: 'u-member', email: 'member@example.test' };
const flags = stage => [{ feature: 'openchat_23', stage, owner_ids: ['owner@example.test'], reviewer_ids: [] }];
const rows = [
  { id: 'a', chat_title: '23再生AP/MSにチャレンジ!!【神大家】', route_id: '23_saisei_ap_ms_challenge_g' },
  { id: 'b', chat_title: '20戸建にチャレンジ!G【神大家】', route_id: '20_kodate_challenge_g' },
  { id: 'c', chat_title: null, chat_name: '23再生AP/MSにチャレンジ!!【神大家】', route_id: null },
  { id: 'd', chat_title: 'x', route_id: '23_saisei_ap_ms_challenge_g' },
];

test('松野さんのみの段階: 名指しの人だけに23番が出て、会員・不明な人には出ない', () => {
  assert.equal(needsViewer(flags('owner')), true);
  assert.deepEqual(filterOpenchatRows(rows, hiddenOpenchats(flags('owner'), owner)).map(r => r.id), ['a', 'b', 'c', 'd']);
  assert.deepEqual(filterOpenchatRows(rows, hiddenOpenchats(flags('owner'), member)).map(r => r.id), ['b']);
  assert.deepEqual(filterOpenchatRows(rows, hiddenOpenchats(flags('owner'), null)).map(r => r.id), ['b']);
});

test('スイッチが無い・読めない・知らない段階なら誰にも出さない。全員公開なら本人確認なしで出す', () => {
  for (const f of [null, [], flags('off'), flags('bogus')]) {
    assert.deepEqual(filterOpenchatRows(rows, hiddenOpenchats(f, owner)).map(r => r.id), ['b']);
  }
  assert.equal(needsViewer(flags('all')), false);
  assert.equal(hiddenOpenchats(flags('all'), null).length, 0);
});

test('答えの使い回しを止める目印は23番の行だけに付く', () => {
  assert.equal(isRestrictedOpenchat(rows[0]), true);
  assert.equal(isRestrictedOpenchat(rows[1]), false);
});

test('ログイン証明: 正しい署名・期限内だけ会員IDを返す', async () => {
  const secret = 's'.repeat(40);
  const now = Date.UTC(2026, 10, 18);
  const token = await issueSession('u-owner', secret, now);
  assert.equal(await viewerFromToken(token, secret, now + 1000), 'u-owner');
  assert.equal(await viewerFromToken(token, 't'.repeat(40), now), null);
  assert.equal(await viewerFromToken(token, secret, now + 9 * 3600 * 1000), null);
  assert.equal(await viewerFromToken(token.replace(/^./, 'x'), secret, now), null);
  assert.equal(await viewerFromToken('', secret, now), null);
});
