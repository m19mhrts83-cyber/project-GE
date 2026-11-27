import { test } from 'node:test';
import assert from 'node:assert/strict';
import { ratioOf, buildRows, weekStartOf } from '../lib/timeUse.ts';

const w = (week_start, steering, clarity, policy, needless) => ({ week_start, steering, clarity, policy, needless, memo: '', source: '' });

test('聞くまでもない確認の割合 = 聞くまでもない確認 ÷ 4区分の合計。0件なら null', () => {
  assert.equal(ratioOf(w('x', 9, 4, 3, 3)), 3 / 19);
  assert.equal(ratioOf(w('x', 0, 0, 0, 0)), null);
  assert.equal(ratioOf(w('x', 5, 0, 0, 0)), 0);
});

test('週の開始日順に並べ、合計と割合を出す', () => {
  const rows = buildRows([w('2026-11-30', 4, 2, 2, 2), w('2026-11-23', 9, 4, 3, 3)]);
  assert.deepEqual(rows.map((r) => r.week_start), ['2026-11-23', '2026-11-30']);
  assert.equal(rows[1].ratio, 0.2);
  assert.equal(rows[1].total, 10);
});

test('週の開始日は月曜（JST）', () => {
  assert.equal(weekStartOf(new Date('2026-11-27T09:00:00Z')), '2026-11-23');
  assert.equal(weekStartOf(new Date('2026-11-22T16:00:00Z')), '2026-11-23');
});
