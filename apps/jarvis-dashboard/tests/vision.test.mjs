import { test } from 'node:test';
import assert from 'node:assert/strict';
import { parseVision } from '../lib/vision.ts';

test('空なら null（欄ごと出さない）', () => {
  assert.equal(parseVision(''), null);
  assert.equal(parseVision(null), null);
  assert.equal(parseVision('## 見出しだけ\n'), null);
});

test('V行・補足・注記に分ける', () => {
  const v = parseVision('## h\nV1. あ: い\nV2. う:\n  - え\n  - お\n注記\n');
  assert.equal(v.items.length, 2);
  assert.equal(v.items[0].id, 'V1');
  assert.deepEqual(v.items[1].sub, ['え', 'お']);
  assert.deepEqual(v.notes, ['注記']);
});
