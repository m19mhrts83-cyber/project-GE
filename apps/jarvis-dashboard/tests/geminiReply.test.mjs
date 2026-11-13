import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

// 2026-11-13: 従量課金の Gemini API を呼ばないことを確かめる（定額 AI への依頼だけ）。
test('geminiReply no longer calls a metered AI API', () => {
  for (const f of ['lib/geminiReply.ts', 'lib/flatAi.ts', 'app/actions/triage.ts']) {
    const src = readFileSync(new URL(`../${f}`, import.meta.url), 'utf8');
    assert.ok(!src.includes('generativelanguage.googleapis.com'), `${f} calls Gemini API`);
    assert.ok(!/api\.openai\.com|api\.anthropic\.com/.test(src), `${f} calls a metered API`);
  }
});

test('flatPromptHash is stable and image-aware', async () => {
  const { flatPromptHash } = await import('../lib/flatAiHash.ts');
  assert.equal(flatPromptHash('a'), flatPromptHash('a'));
  assert.notEqual(flatPromptHash('a'), flatPromptHash('b'));
  assert.notEqual(flatPromptHash('a'), flatPromptHash('a', [{ mimeType: 'image/png', base64: 'xx' }]));
});
