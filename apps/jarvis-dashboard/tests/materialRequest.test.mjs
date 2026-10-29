import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';

function load() {
  const source = readFileSync(new URL('../lib/materialRequest.ts', import.meta.url), 'utf8');
  const code = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText;
  const exports = {};
  vm.runInNewContext(code, { exports });
  return exports.extractMaterialRequests;
}

test('下記の書類一覧を品目として拾う（Python と同じ結果）', () => {
  const e = load();
  const body = '松野様\n\n下記の書類のご準備をお願いします。\n\n借入申込書（お渡ししたもの）\n今期の試算表\n通帳のコピー\n\nよろしくお願いいたします。\n';
  assert.deepEqual([...e(body)], ['借入申込書（お渡ししたもの）', '今期の試算表', '通帳のコピー']);
});

test('番号付き一覧と区切り線、引用は拾わない', () => {
  const e = load();
  const body = '下記追加資料のご提出をお願いいたします。\n＝＝＝\n1. 物件住所のページ\n2. 所有者の確認\n＝＝＝\n※補足\n\n2026年10月21日(水) 7:21 松野家 <a@b.c>:\n> ・引用の書類\n';
  assert.deepEqual([...e(body)], ['物件住所のページ', '所有者の確認']);
});

test('依頼でないメールは空', () => {
  const e = load();
  assert.equal(e('松野様\n立ち会いは明日14時です。\nよろしくお願いいたします。').length, 0);
});
