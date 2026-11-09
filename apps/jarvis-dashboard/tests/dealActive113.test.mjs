import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import {
  d113ButtonValue,
  nextD113State,
  parseD113ButtonValue,
  replaceDecidedRow,
} from '../lib/dealActive113Core.ts';

const DEAL = '11111111-2222-3333-4444-555555555555';
const ENV = { PROPERTY_GATE_ACTION_TOKEN: 's3cret' };

test('signature matches the Python side (scripts/kurashift_deal_active_113.py)', () => {
  // python: d113_value('s3cret', 'pass', DEAL)
  assert.equal(d113ButtonValue('pass', DEAL, ENV), `d113:pass:${DEAL}:52900d74dc`);
  assert.deepEqual(parseD113ButtonValue(`d113:pass:${DEAL}:52900d74dc`, ENV), {
    action: 'pass',
    dealId: DEAL,
  });
});

test('dedicated token is preferred but the shared token still verifies', () => {
  const env = { DEAL_ACTIVE_113_ACTION_TOKEN: 'own', PROPERTY_GATE_ACTION_TOKEN: 's3cret' };
  const v = d113ButtonValue('hold', DEAL, env);
  assert.ok(parseD113ButtonValue(v, env));
  assert.ok(parseD113ButtonValue(`d113:pass:${DEAL}:52900d74dc`, env));
});

test('tampered or foreign values are rejected', () => {
  assert.equal(parseD113ButtonValue(`d113:pass:${DEAL}:0000000000`, ENV), null);
  assert.equal(parseD113ButtonValue(`d113:delete:${DEAL}:52900d74dc`, ENV), null);
  assert.equal(parseD113ButtonValue(`t312:create:abc:52900d74dc`, ENV), null);
  assert.equal(parseD113ButtonValue(`d113:pass:${DEAL}:52900d74dc`, {}), null);
});

test('state transitions', () => {
  const base = { ts: '1.1', state: 'needs_check', asked_count: 2 };
  const c = nextD113State(base, 'continue', '2026-11-09');
  assert.equal(c.state, 'active');
  assert.equal(c.next_check_at, '2026-11-23');
  assert.equal(c.asked_count, 0);
  assert.equal(nextD113State(base, 'hold', '2026-11-09').next_check_at, '2026-12-09');
  const p = nextD113State(base, 'pass', '2026-11-09');
  assert.equal(p.state, 'closed');
  assert.equal(p.closed_at, '2026-11-09');
  assert.equal(p.closed_reason, 'pass');
  assert.equal(nextD113State(base, 'done', '2026-11-09').closed_reason, 'done');
});

test('only the pressed row is replaced', () => {
  const blocks = [
    { type: 'section', block_id: 'x' },
    { type: 'actions', block_id: `d113_${DEAL}` },
    { type: 'actions', block_id: 'd113_other' },
  ];
  const out = replaceDecidedRow(blocks, DEAL, 'continue', 'U1');
  assert.equal(out[1].type, 'context');
  assert.match(out[1].elements[0].text, /続ける/);
  assert.equal(out[2].type, 'actions');
});

test('route sends d113 values to the 113 handler', () => {
  const route = readFileSync(
    new URL('../app/api/slack/consult-action/route.ts', import.meta.url),
    'utf8',
  );
  assert.match(route, /startsWith\("d113:"\)/);
  assert.match(route, /handleD113BlockAction/);
});
