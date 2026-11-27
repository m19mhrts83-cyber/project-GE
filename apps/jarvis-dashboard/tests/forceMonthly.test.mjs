import { test } from 'node:test';
import assert from 'node:assert/strict';
import { parseForceMonthly, parseAdvisoryFee, monthRows } from '../lib/forceMonthly.ts';

const raw = JSON.stringify({
  generated_at: '2026-11-28T10:00:00+09:00',
  months: ['2026-10', '2026-11'],
  services: [
    { id: 'claude', label: 'Claude', group: 'ai' },
    { id: 'supabase', label: 'Supabase', group: 'base' },
  ],
  amounts: { '2026-10': { claude: 100 }, '2026-11': { claude: 300, supabase: 100 } },
  usage: null,
});

test('AI と基盤を分けて合計し、収入のある月だけ差と比率を出す', () => {
  const rows = monthRows(parseForceMonthly(raw), parseAdvisoryFee(JSON.stringify({ fixed_yen: 900, fixed_from: '2026-11', extras: { '2026-11': 100 } })));
  assert.deepEqual([rows[0].ai, rows[0].base, rows[0].diff, rows[0].ratioPct], [100, 0, null, null]);
  assert.deepEqual([rows[1].ai, rows[1].base, rows[1].total, rows[1].diff, rows[1].ratioPct], [300, 100, 400, 600, 40]);
  assert.equal(rows[1].blockedDays, null);
});

test('壊れた値は null', () => {
  assert.equal(parseForceMonthly('{'), null);
  assert.equal(parseForceMonthly(null), null);
});

test('固定は開始月から・追加だけの月も見合いに出る', () => {
  const fee = parseAdvisoryFee(JSON.stringify({ fixed_yen: 900, fixed_from: '2026-11', extras: { '2026-10': 50, bad: 1 } }));
  const rows = monthRows(parseForceMonthly(raw), fee);
  assert.deepEqual([rows[0].fixed, rows[0].extra, rows[0].income], [null, 50, 50]);
  assert.deepEqual([rows[1].fixed, rows[1].extra, rows[1].income], [900, null, 900]);
  assert.equal(parseAdvisoryFee('x'), null);
});
