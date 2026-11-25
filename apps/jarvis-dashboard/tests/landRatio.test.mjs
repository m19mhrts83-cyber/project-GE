import { test } from 'node:test';
import assert from 'node:assert/strict';
import { usableLandRatioText } from '../lib/landRatio.ts';

test('文章中の数字は率として使わない', () => {
  assert.equal(usableLandRatioText('算定不可'), null);
  assert.equal(usableLandRatioText('未取得（〇〇サイトが404）'), null);
  assert.equal(usableLandRatioText('不明（固評依頼要）'), null);
  assert.equal(usableLandRatioText(''), null);
});

test('正常な率表記はそのまま使う', () => {
  assert.equal(usableLandRatioText('123.4%'), '123.4%');
  assert.equal(usableLandRatioText('1.87'), '1.87');
  assert.equal(usableLandRatioText('参考1.2（確定不可）'), '参考1.2（確定不可）');
  assert.equal(usableLandRatioText('約90%'), '約90%');
});
