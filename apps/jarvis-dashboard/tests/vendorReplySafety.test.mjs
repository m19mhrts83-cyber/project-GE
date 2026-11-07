import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const routeSource = readFileSync(
  new URL('../app/api/g/vr/[action]/[id]/route.ts', import.meta.url),
  'utf8',
);
const actionSource = readFileSync(
  new URL('../lib/vendorReplySlackAction.ts', import.meta.url),
  'utf8',
);

test('GET signed-link route is read-only and renders a POST confirmation form', () => {
  const getSection = routeSource
    .split('export async function GET', 2)[1]
    .split('export async function POST', 1)[0];
  assert.ok(getSection.includes('confirmActionHtml'));
  assert.ok(!getSection.includes('applyVendorReplySlack('));
  assert.match(actionSource, /<form method="POST"/);
});

test('legacy short-link source is explicitly rejected', () => {
  assert.match(actionSource, /source === "slack_short_link"/);
  assert.match(actionSource, /isBlockedVendorReplyRecipient\(to\)/);
});
