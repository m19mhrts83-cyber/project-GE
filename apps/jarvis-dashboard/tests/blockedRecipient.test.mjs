import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  isBlockedRecipient,
  assertSendableRecipients,
  BlockedRecipientError,
} from '../lib/gmail/blockedRecipient.ts';
import { readFileSync } from 'node:fs';

test('noreply 系・mailer-daemon・google.com は禁止', () => {
  for (const a of [
    'noreply@example.com',
    'no-reply@example.com',
    'do-not-reply@example.com',
    'noreply-accounts@example.com',
    'MAILER-DAEMON@example.com',
    'someone@' + 'google.com',
    'x@accounts.' + 'google.com',
  ]) {
    assert.equal(isBlockedRecipient(a), true, a);
  }
});

test('通常の宛先は通す', () => {
  for (const a of ['agent@example.co.jp', 'replyto@example.com', 'a@mygoogle.com.example.jp']) {
    assert.equal(isBlockedRecipient(a), false, a);
  }
});

test('複数宛先・名前付きでも1件でも禁止なら投げる', () => {
  assert.throws(
    () => assertSendableRecipients('ok@example.com, Bot <no-reply@example.com>'),
    BlockedRecipientError,
  );
  assert.doesNotThrow(() => assertSendableRecipients('ok@example.com; Name <b@example.org>'));
});

test('sendGmailViaEnv は Gmail API 呼び出し前にガードを通る', () => {
  const src = readFileSync(new URL('../lib/gmail/sendFromEnv.ts', import.meta.url), 'utf8');
  const fn = src.split('export async function sendGmailViaEnv')[1];
  assert.ok(fn.indexOf('assertSendableRecipients(opts.to)') < fn.indexOf('gmailClientFromEnv'));
});
