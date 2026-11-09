import { test } from 'node:test';
import assert from 'node:assert/strict';
import { loadLib } from './load.mjs';

const z = loadLib('zaimCore');
const plain = (x) => JSON.parse(JSON.stringify(x));

const payload = {
  review_batch_id: 'b2',
  dashboard_ack_batch_id: 'b1',
  recent_fixes: [
    { id: 'f1', status: 'pending_confirm', batch_id: 'b1', proposal: '確認済みの束' },
    { id: 'f2', status: 'pending_confirm', proposal: 'セブン ¥500: 雑費 → 食費', amount: 500 },
    { id: 'f3', status: 'confirmed' },
    { id: 'f4', proposal: '状態なし' },
  ],
};

test('確認待ち: 確認済みの束と確定済みは出さない', () => {
  assert.deepEqual(plain(z.pendingFixes(payload).map((f) => f.id)), ['f2', 'f4']);
});

test('正しい／違う を反映して件数を数え直す', () => {
  const { payload: p, found } = z.applyVerdict(payload, 'f2', 'disputed', '2026-11-08T00:00:00Z');
  assert.equal(found, true);
  const f2 = p.recent_fixes.find((f) => f.id === 'f2');
  assert.equal(f2.status, 'disputed');
  assert.equal(f2.batch_id, 'b2');
  assert.equal(p.pending_confirm_count, 2); // f2(disputed) と f4
  assert.equal(z.applyVerdict(payload, 'nope', 'confirmed', 'x').found, false);
});
