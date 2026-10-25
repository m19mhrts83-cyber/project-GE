import { test } from 'node:test';
import assert from 'node:assert/strict';
import { geminiReply } from '../lib/geminiReply.ts';

test('Gemini bounds and error handling without network', async (t) => {
  const originalFetch = globalThis.fetch;
  const originalKey = process.env.GEMINI_API_KEY;
  process.env.GEMINI_API_KEY = 'test-only';
  t.after(() => {
    globalThis.fetch = originalFetch;
    if (originalKey === undefined) delete process.env.GEMINI_API_KEY;
    else process.env.GEMINI_API_KEY = originalKey;
  });
  for (const status of [401, 429, 500]) {
    let calls = 0;
    globalThis.fetch = async () => { calls++; return new Response('SECRET_SENTINEL', { status }); };
    const result = await geminiReply('test', { maxAttempts: 2 });
    assert.equal(result.ok, false);
    assert.equal(calls, 1);
    assert.ok(!result.error.includes('SECRET_SENTINEL'));
  }
  let calls = 0;
  globalThis.fetch = async () => { calls++; return new Response('', { status: 404 }); };
  await geminiReply('test', { maxAttempts: 2 });
  assert.equal(calls, 2);
  calls = 0;
  globalThis.fetch = async () => { calls++; throw new Error('SECRET_SENTINEL'); };
  assert.equal((await geminiReply('test')).ok, false);
  assert.equal(calls, 1);
  globalThis.fetch = async () => new Response('invalid-json');
  assert.equal((await geminiReply('test')).ok, false);
  globalThis.fetch = async (_url, options) => {
    assert.equal(JSON.parse(options.body).generationConfig.maxOutputTokens, 2048);
    assert.ok(options.signal);
    return Response.json({ candidates: [{ content: { parts: [{ text: 'answer' }] } }] });
  };
  assert.deepEqual(await geminiReply('test', { maxOutputTokens: 2048 }), { ok: true, text: 'answer' });
});
