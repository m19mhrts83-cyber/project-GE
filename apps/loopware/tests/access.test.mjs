import { test } from 'node:test';
import assert from 'node:assert/strict';
import { loadLib } from './load.mjs';

const a = loadLib('access');

test('鍵が合う Cookie だけ通す', async () => {
  const v = await a.sessionValue('k1');
  assert.equal(await a.isValidSession('k1', v), true);
  assert.equal(await a.isValidSession('k2', v), false);
  assert.equal(await a.isValidSession('', v), false);
  assert.equal(await a.isValidSession('k1', ''), false);
});

test('リンクの t= は期限内・同じ鍵だけ通す', async () => {
  const now = new Date('2026-11-08T00:00:00Z');
  const t = await a.linkToken('k1', now, 7);
  assert.equal(await a.isValidLinkToken('k1', t, now), true);
  assert.equal(await a.isValidLinkToken('k2', t, now), false);
  assert.equal(await a.isValidLinkToken('k1', t, new Date('2026-11-16T00:00:00Z')), false);
  assert.equal(await a.isValidLinkToken('k1', 'abc', now), false);
  const [exp, sig] = t.split('.');
  assert.equal(await a.isValidLinkToken('k1', `${Number(exp) + 999}.${sig}`, now), false);
});

test('鍵なしで開いてよいのは従来の画面だけ', () => {
  assert.equal(a.isLegacyOpenPath('/313'), true);
  assert.equal(a.isLegacyOpenPath('/api/decide'), true);
  assert.equal(a.isLegacyOpenPath('/desk'), false);
  assert.equal(a.isLegacyOpenPath('/all'), false);
  assert.equal(a.isLegacyOpenPath('/api/all'), false);
  assert.equal(a.isLegacyOpenPath('/api/log'), false);
  assert.equal(a.isLegacyOpenPath('/api/misses'), true);
  assert.equal(a.isLegacyOpenPath('/api/misses', new URLSearchParams('surface=triage')), false);
  assert.equal(a.isPublicPath('/login'), true);
});

test('ボット用の鍵: 別の Cookie で actor=bot、松野さんの鍵は owner', async () => {
  const owner = await a.sessionValue('owner-key');
  const bot = await a.botSessionValue('bot-key');
  assert.notEqual(owner, bot);
  assert.equal(await a.actorFromCookie('owner-key', 'bot-key', owner), 'owner');
  assert.equal(await a.actorFromCookie('owner-key', 'bot-key', bot), 'bot');
  assert.equal(await a.actorFromCookie('owner-key', 'bot-key', 'x'), null);
  assert.equal(await a.actorFromCookie('owner-key', 'bot-key', ''), null);
});

test('ボット用の鍵が未設定・松野さんの鍵と同じなら、ボットは入れない', async () => {
  const bot = await a.botSessionValue('bot-key');
  assert.equal(await a.actorFromCookie('owner-key', '', bot), null);
  assert.equal(await a.actorFromCookie('owner-key', undefined, bot), null);
  // 同じ鍵なら owner の Cookie が先に当たり、ボット扱いにはならない
  assert.equal(a.usableBotKey('same', 'same'), '');
  assert.equal(await a.actorFromCookie('same', 'same', await a.sessionValue('same')), 'owner');
  // 鍵を変えれば古いボット Cookie は無効
  assert.equal(await a.actorFromCookie('owner-key', 'bot-key2', bot), null);
});

test('ボットを止める 403 の本文', () => {
  assert.equal(a.BOT_FORBIDDEN_BODY.code, 'bot_forbidden');
  assert.equal(a.BOT_FORBIDDEN_BODY.ok, false);
});
