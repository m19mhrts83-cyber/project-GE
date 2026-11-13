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

test('下書き作成はやり取り履歴と資料依頼をプロンプトに入れる', async () => {
  let prompt = '';
  const m = load(async (p) => { prompt = p; return { ok: true, text: '山村様\n\nご連絡ありがとうございます。\n\n松野' }; });
  const r = await m.composeDraft({
    who: '山村不動産',
    subject: '物件の件',
    inbound: '松野様\n資料をお送りください。',
    history: '【OneDrive やり取り末尾】前回の打合せ',
    materials: ['登記簿謄本'],
  });
  assert.equal(r.ok, true);
  assert.match(r.text, /^山村様/);
  assert.match(prompt, /これまでのやり取り/);
  assert.match(prompt, /前回の打合せ/);
  assert.match(prompt, /添付して送る前提/);
});

test('下書き作成は元のメールが空なら呼ばない', async () => {
  let called = false;
  const m = load(async () => { called = true; return { ok: true, text: 'x' }; });
  const r = await m.composeDraft({ who: 'a', subject: 'b', inbound: '  ' });
  assert.equal(r.ok, false);
  assert.equal(called, false);
});

test('本文が空のときの下書き作成は指示をプロンプトに入れる', async () => {
  let prompt = '';
  const m = load(async (p) => { prompt = p; return { ok: true, text: '承知しました。\n松野' }; });
  const r = await m.composeDraft({ who: '山田様', subject: '件名', inbound: 'ご確認ください', instruction: 'お礼だけ短く' });
  assert.equal(r.ok, true);
  assert.match(prompt, /松野さんの指示/);
  assert.match(prompt, /お礼だけ短く/);
});

test('指示なしなら指示ブロックを入れない', () => {
  const m = load(async () => ({ ok: false, error: 'x' }));
  const p = m.composePrompt({ who: 'A', subject: 'B', inbound: 'C' });
  assert.doesNotMatch(p, /松野さんの指示/);
});

test('チャット（LINE）は宛名・署名なしの短文の指示になる', () => {
  const m = load(async () => ({ ok: false, error: 'x' }));
  const p = m.composePrompt({ who: 'Tcell', subject: '', inbound: '鍵の件どうなりましたか', chat: 'LINE' });
  assert.match(p, /LINEで届いたメッセージ/);
  assert.match(p, /宛名（〇〇様）・署名/);
  assert.doesNotMatch(p, /末尾署名は「松野」のみ/);
});
