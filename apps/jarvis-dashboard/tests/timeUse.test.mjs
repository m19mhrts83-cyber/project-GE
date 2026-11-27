import { test } from 'node:test';
import assert from 'node:assert/strict';
import { ratioOf, buildRows, weekStartOf } from '../lib/timeUse.ts';

test('判断の比率は 判断/(判断+直し)。0件なら null', () => {
  assert.equal(ratioOf(12, 4), 0.75);
  assert.equal(ratioOf(0, 0), null);
});

test('週の開始日順に並べ、方針づくりは比率に入らない', () => {
  const rows = buildRows([
    { week_start: '2026-11-30', decisions: 5, fixes: 5, policy: 99, memo: '', source: '' },
    { week_start: '2026-11-23', decisions: 12, fixes: 4, policy: 3, memo: '', source: '' },
  ]);
  assert.deepEqual(rows.map((r) => r.week_start), ['2026-11-23', '2026-11-30']);
  assert.equal(rows[1].ratio, 0.5);
});

test('週の開始日は月曜（JST）', () => {
  assert.equal(weekStartOf(new Date('2026-11-27T09:00:00Z')), '2026-11-23');
  assert.equal(weekStartOf(new Date('2026-11-22T16:00:00Z')), '2026-11-23');
});
