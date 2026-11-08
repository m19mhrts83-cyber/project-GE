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
  assert.equal(a.isLegacyOpenPath('/api/log'), false);
  assert.equal(a.isPublicPath('/login'), true);
});
