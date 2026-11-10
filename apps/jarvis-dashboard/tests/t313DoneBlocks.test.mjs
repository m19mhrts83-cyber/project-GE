import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';

function load() {
  const source = readFileSync(new URL('../lib/t313DoneBlocks.ts', import.meta.url), 'utf8');
  const code = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText;
  const exports = {};
  vm.runInNewContext(code, { exports, Array, Object, String });
  return exports;
}

const blocks = () => [
  { type: 'header' },
  { type: 'section', text: { type: 'mrkdwn', text: '#1' } },
  { type: 'actions', block_id: 't313_clean_A_1', elements: [{}, {}, {}] },
  { type: 'section', text: { type: 'mrkdwn', text: '#2' } },
  { type: 'actions', block_id: 't313_clean_B_2', elements: [{}, {}] },
];

test('成功: 押した行のボタンだけ「報告済み」に替わり、他の行は残る', () => {
  const m = load();
  const out = m.markT313RowDone(blocks(), 't313_clean_A_1', m.t313DoneLabel('close', true), true);
  assert.equal(out.length, 5);
  assert.equal(out[2].type, 'context');
  assert.match(out[2].elements[0].text, /報告済み/);
  assert.equal(out[4].type, 'actions');
});

test('失敗: ボタンは残し、失敗の一言を足す（重ねて押しても1つだけ）', () => {
  const m = load();
  const label = m.t313DoneLabel('reschedule', false, '2026-11-20');
  let out = m.markT313RowDone(blocks(), 't313_clean_B_2', label, false);
  out = m.markT313RowDone(out, 't313_clean_B_2', label, false);
  assert.equal(out.length, 6);
  assert.equal(out[4].type, 'actions');
  assert.equal(out[5].type, 'context');
  assert.match(out[5].elements[0].text, /失敗/);
});

test('行が見つからなければ null（従来の ephemeral に戻す）', () => {
  const m = load();
  assert.equal(m.markT313RowDone(blocks(), 'nope', 'x', true), null);
  assert.equal(m.markT313RowDone([], '', 'x', true), null);
});

test('延期ラベルに日付が入る', () => {
  const m = load();
  assert.match(m.t313DoneLabel('reschedule', true, '2026-11-20'), /2026-11-20 へ延期/);
});
