import { test } from 'node:test';
import assert from 'node:assert/strict';
import { loadLib } from './load.mjs';

const sp = loadLib('senderPolicyCore');
const plain = (x) => JSON.parse(JSON.stringify(x));

test('送り手のキー（名前つき・大文字・アドレスなし）', () => {
  assert.equal(sp.senderKey('山本 <Yamamoto@Ex.JP>'), 'from:yamamoto@ex.jp');
  assert.equal(sp.senderKey('a@b.jp'), 'from:a@b.jp');
  assert.equal(sp.senderKey('名前だけ'), null);
  assert.equal(sp.senderKey(''), null);
});

test('設定の読み込み（文字列・壊れた値・知らない設定は捨てる）', () => {
  const raw = JSON.stringify({ entries: { 'from:a@b.jp': { policy: 'hide', at: 't' }, 'from:c@d.jp': { policy: 'bad' } } });
  const m = sp.parsePolicies(raw);
  assert.deepEqual(plain(Object.keys(m)), ['from:a@b.jp']);
  assert.deepEqual(plain(sp.parsePolicies('{oops')), {});
  assert.deepEqual(plain(sp.parsePolicies(null)), {});
});

test('デスクから外すのは 出さない／自動で回答不要 だけ（毎回見るは出す）', () => {
  let m = {};
  m = sp.withPolicy(m, 'x <a@b.jp>', 'hide', 't1');
  m = sp.withPolicy(m, 'c@d.jp', 'auto_done', 't2');
  m = sp.withPolicy(m, 'e@f.jp', 'always', 't3');
  assert.equal(sp.hiddenFromDesk(m, 'A@B.jp'), true);
  assert.equal(sp.hiddenFromDesk(m, 'c@d.jp'), true);
  assert.equal(sp.hiddenFromDesk(m, 'e@f.jp'), false);
  assert.equal(sp.hiddenFromDesk(m, 'z@z.jp'), false);
  // 上書き
  m = sp.withPolicy(m, 'a@b.jp', 'always', 't4');
  assert.equal(sp.hiddenFromDesk(m, 'a@b.jp'), false);
});
