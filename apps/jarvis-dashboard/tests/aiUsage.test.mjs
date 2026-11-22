import { test } from 'node:test';
import assert from 'node:assert/strict';
import { parseAiUsage, viewRows, viewVerdicts, ageText, historyRows } from '../lib/aiUsage.ts';

const NOW = Date.parse('2026-11-22T13:30:00Z');
const payload = (observedAt, resetsAt = '2026-11-24T22:00:00Z') => JSON.stringify({
  generated_at: '2026-11-22T13:25:00Z',
  rows: [{ agent: 'claude', agent_label: 'Claude', window: 'weekly', label: '週枠', used_percent: 50, resets_at: resetsAt, observed_at: observedAt }],
  verdicts: [{ agent: 'claude', level: 'keep', title: 'Claude：Max が要ります', detail: 'x' }],
  history: { 'claude.weekly': [{ resets_at: '2026-11-17T22:00:00Z', peak: 12 }, { resets_at: '2026-11-24T22:00:00Z', peak: 50 }] },
  assumptions: { stale_min: 180 },
});

test('新しい値はそのまま判断に使う', () => {
  const p = parseAiUsage(payload('2026-11-22T13:20:00Z'));
  const rows = viewRows(p, NOW);
  assert.equal(rows[0].stale, false);
  assert.equal(viewVerdicts(p, rows)[0].level, 'keep');
});

test('写してから時間がたった値は、判断できないに落とす', () => {
  const p = parseAiUsage(payload('2026-11-22T13:20:00Z'));
  const later = NOW + 5 * 3600 * 1000;
  const rows = viewRows(p, later);
  assert.equal(rows[0].stale, true);
  const v = viewVerdicts(p, rows)[0];
  assert.equal(v.level, 'unknown');
  assert.match(v.detail, /50%/);
});

test('回復時刻を過ぎた値も、判断できないに落とす', () => {
  const p = parseAiUsage(payload('2026-11-22T13:20:00Z', '2026-11-22T13:25:00Z'));
  const rows = viewRows(p, NOW);
  assert.equal(rows[0].resetPassed, true);
  assert.equal(viewVerdicts(p, rows)[0].level, 'unknown');
});

test('壊れた値・空は null', () => {
  assert.equal(parseAiUsage(undefined), null);
  assert.equal(parseAiUsage('{'), null);
  assert.equal(parseAiUsage('{"rows":1}'), null);
});

test('履歴は新しい順、終わった枠に印', () => {
  const h = historyRows(parseAiUsage(payload('2026-11-22T13:20:00Z')), 'claude.weekly', NOW);
  assert.deepEqual(h.map((e) => [e.peak, e.closed]), [[50, false], [12, true]]);
});

test('古さの表示', () => {
  assert.equal(ageText(5), '5分前');
  assert.equal(ageText(300), '5時間前');
  assert.equal(ageText(5514), '3日前');
  assert.equal(ageText(null), '時刻不明');
});
