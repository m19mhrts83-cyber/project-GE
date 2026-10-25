import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';
import crypto from 'node:crypto';

// 実ソースを変換し、ネットワーク境界だけを差し替える。
function load(env, gemini, cloud, records = []) {
  const source = readFileSync(new URL('../lib/askEngine.ts', import.meta.url), 'utf8');
  const code = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText;
  const exports = {};
  vm.runInNewContext(code, { exports, console: { info: message => records.push(JSON.parse(message)) }, process: { env }, require: name => {
    if (name === 'node:crypto') return crypto;
    if (name === '@/lib/geminiReply') return { geminiReply: gemini };
    if (name === '@/lib/cursor/cloudAsk') return { askWithCloudAgent: cloud, CLOUD_ASK_TIMEOUT_MS: 1000 };
    throw new Error(`Unexpected dependency ${name}`);
  }});
  return exports.resolveAskReply;
}

test('auto: keys alone never authorize API calls', async () => {
  const forbidden = () => { throw new Error('network must not be called'); };
  const resolve = load({ CURSOR_API_KEY: 'test', GEMINI_API_KEY: 'test' }, forbidden, forbidden);
  const result = await resolve({ engine: 'auto', prompt: 'question' });
  assert.equal(result.needLocal, true);
});

test('cache isolates users and invalidates changed source content', async () => {
  let calls = 0;
  const resolve = load({ ASK_AUTO_ALLOW_GEMINI: '1' }, async () => { calls++; return { ok: true, text: 'answer' }; }, null);
  const request = { engine: 'auto', prompt: 'source v1 question', cacheScope: 'user-a:card-1' };
  await resolve(request);
  await resolve(request);
  assert.equal(calls, 1);
  await resolve({ ...request, cacheScope: 'user-b:card-1' });
  await resolve({ ...request, prompt: 'source v2 question' });
  assert.equal(calls, 3);
  await resolve({ ...request, cacheScope: undefined });
  await resolve({ ...request, cacheScope: undefined });
  assert.equal(calls, 5);
});

test('usage record excludes content and reports unknown cost honestly', async () => {
  const records = [];
  const resolve = load({ ASK_AUTO_ALLOW_GEMINI: '1' }, async () => { throw new Error('SECRET_ERROR'); }, null, records);
  const result = await resolve({ engine: 'auto', prompt: 'SECRET_PROMPT' });
  assert.equal(result.needLocal, true);
  assert.equal(records.length, 1);
  assert.equal(records[0].input_chars, 13);
  assert.equal(records[0].cost, null);
  assert.ok(!JSON.stringify(records).includes('SECRET'));
  assert.ok(!JSON.stringify(result).includes('SECRET'));
});

test('auto: lightweight success avoids Cloud', async () => {
  const calls = [];
  const resolve = load({ ASK_AUTO_ALLOW_GEMINI: '1', ASK_AUTO_ALLOW_CLOUD: '1', CURSOR_API_KEY: 'test' }, async (_, opts) => {
    calls.push('gemini'); assert.equal(opts.maxAttempts, 1); return { ok: true, text: 'answer' };
  }, () => { throw new Error('Cloud must not be called'); });
  assert.equal((await resolve({ engine: 'auto', prompt: 'question' })).via, 'gemini');
  assert.deepEqual(calls, ['gemini']);
});

test('auto: failure escalates once only to authorized Cloud', async () => {
  const calls = [];
  const resolve = load({ ASK_AUTO_ALLOW_GEMINI: '1', ASK_AUTO_ALLOW_CLOUD: '1', CURSOR_API_KEY: 'test' }, async () => {
    calls.push('gemini'); return { ok: false, error: 'unavailable' };
  }, async () => { calls.push('cloud'); return { ok: false, error: 'unavailable' }; });
  assert.equal((await resolve({ engine: 'auto', prompt: 'question' })).needLocal, true);
  assert.deepEqual(calls, ['gemini', 'cloud']);
});
