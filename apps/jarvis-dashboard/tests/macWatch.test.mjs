import { test } from 'node:test';
import assert from 'node:assert/strict';
import { decide, isStale, STALE_MS } from '../lib/macWatch.ts';

const NOW = Date.parse('2026-11-28T03:00:00Z');
const ago = (min) => new Date(NOW - min * 60000).toISOString();

test('止まり判定は 15 分: 12 分前は生きている、16 分前と未受信は止まり', () => {
  assert.equal(STALE_MS, 15 * 60 * 1000);
  assert.equal(isStale(ago(12), NOW), false);
  assert.equal(isStale(ago(16), NOW), true);
  assert.equal(isStale(null, NOW), true);
  assert.equal(isStale('not-a-date', NOW), true);
});

test('1 回だけ止まりなら通知しない（瞬断）', () => {
  assert.deepEqual(decide('online', 0, true), { state: 'online', streak: 1, notify: null });
});

test('2 回連続で止まりなら 🔴 を 1 回', () => {
  assert.deepEqual(decide('online', 1, true), { state: 'offline', streak: 2, notify: 'down' });
});

test('止まり続けても重ねて通知しない', () => {
  assert.deepEqual(decide('offline', 2, true), { state: 'offline', streak: 3, notify: null });
});

test('1 回止まりのあと戻れば連続回数を 0 に戻し、通知しない', () => {
  assert.deepEqual(decide('online', 1, false), { state: 'online', streak: 0, notify: null });
});

test('通知済みの止まりから戻れば 🟢 を 1 回（1 回で復旧）', () => {
  assert.deepEqual(decide('offline', 5, false), { state: 'online', streak: 0, notify: 'up' });
});

test('初回（unknown）: online は無言、止まりは 2 回連続で初めて通知', () => {
  assert.deepEqual(decide('unknown', 0, false), { state: 'online', streak: 0, notify: null });
  assert.deepEqual(decide('unknown', 0, true), { state: 'unknown', streak: 1, notify: null });
  assert.deepEqual(decide('unknown', 1, true), { state: 'offline', streak: 2, notify: 'down' });
});
