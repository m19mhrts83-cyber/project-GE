import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';

// 実ソースを変換し、Gemini 呼び出しだけを差し替える。
function load(gemini) {
  const source = readFileSync(new URL('../lib/mailDraftCheck.ts', import.meta.url), 'utf8');
  const code = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText;
  const exports = {};
  vm.runInNewContext(code, { exports, require: name => {
    if (name === '@/lib/geminiReply') return { geminiReply: gemini };
    throw new Error(`Unexpected dependency ${name}`);
  }});
  return exports;
}

test('誤字脱字チェックは修正文と修正点を返す', async () => {
  const m = load(async () => ({ ok: true, text: '```json\n{"text":"お世話になっております。","changes":["おります→おります"]}\n```' }));
  const r = await m.proofreadDraft('お世話になっておりまs。');
  assert.equal(r.ok, true);
  assert.equal(r.text, 'お世話になっております。');
  assert.equal(r.changes.length, 1);
});

test('JSON で返らなければ本文として扱う', () => {
  const m = load(async () => ({ ok: false, error: 'x' }));
  assert.deepEqual(JSON.parse(JSON.stringify(m.parseDraftCheckJson('書き直し本文', '元'))), { text: '書き直し本文', changes: [] });
});

test('見直しは指示が空なら呼ばない', async () => {
  let called = false;
  const m = load(async () => { called = true; return { ok: true, text: '{}' }; });
  const r = await m.reviseDraft('本文', '  ');
  assert.equal(r.ok, false);
  assert.equal(called, false);
});

test('Gemini 失敗時は本文を変えずにエラー', async () => {
  const m = load(async () => ({ ok: false, error: 'HTTP 429' }));
  const r = await m.proofreadDraft('本文');
  assert.equal(r.ok, false);
  assert.match(r.error, /429/);
});
