import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';

function load() {
  const source = readFileSync(new URL('../lib/materialFileSearch.ts', import.meta.url), 'utf8');
  const code = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText;
  const exports = {};
  vm.runInNewContext(code, { exports, Buffer, Date, Math, encodeURIComponent });
  return exports;
}

test('依頼品目からファイル名検索の語を作る', () => {
  const m = load();
  const terms = [...m.searchTermsFromItems(['借入申込書（お渡ししたもの）', '今期の試算表', '通帳のコピー'])];
  assert.deepEqual(terms, ['借入申込書', '今期の試算表', '試算表', '通帳']);
});

test('検索語の指定が先に来て、広すぎる語は外す', () => {
  const m = load();
  const terms = [...m.searchTermsFromItems(['資料一式'], '謄本 2025')];
  assert.deepEqual(terms, ['謄本', '2025']);
});

test('当たった語が多い順、同点は新しい順。重複は1件', () => {
  const m = load();
  const cands = [
    { s: 'od', id: 'a', n: '試算表_2024.pdf', m: '2024-12-01' },
    { s: 'gd', id: 'b', n: '今期の試算表.xlsx', m: '2025-01-01' },
    { s: 'od', id: 'c', n: '試算表_2025.pdf', m: '2025-06-01' },
    { s: 'od', id: 'c', n: '試算表_2025.pdf', m: '2025-06-01' },
  ];
  const r = m.rankCandidates(cands, ['今期の試算表', '試算表']);
  assert.deepEqual([...r].map((x) => x.id), ['b', 'c', 'a']);
});

test('候補の value を往復できる', () => {
  const m = load();
  assert.equal(m.candidateValue({ s: 'od', id: 'ABC!123' }), 'od:ABC!123');
  assert.deepEqual({ ...m.parseCandidateValue('gd:1aB_c-9xyz') }, { s: 'gd', id: '1aB_c-9xyz' });
  assert.equal(m.parseCandidateValue('xx:abc'), null);
});

test('添付なしは text/plain 1パート、添付ありは multipart/mixed', () => {
  const m = load();
  const plain = m.buildMimeMessage({ to: 'a@b.jp', subject: 'Re: 資料', body: '本文' });
  assert.match(plain, /Content-Type: text\/plain; charset=UTF-8\r\n\r\n本文$/);
  assert.match(plain, /Subject: =\?UTF-8\?B\?/);

  const mixed = m.buildMimeMessage({
    to: 'a@b.jp',
    subject: 'Re: 資料',
    body: '本文',
    boundary: 'BB',
    attachments: [{ filename: '謄本.pdf', mimeType: 'application/pdf', data: Buffer.from('PDFDATA') }],
  });
  assert.match(mixed, /Content-Type: multipart\/mixed; boundary="BB"/);
  assert.match(mixed, /filename\*=UTF-8''%E8%AC%84%E6%9C%AC\.pdf/);
  assert.ok(mixed.includes(Buffer.from('PDFDATA').toString('base64')));
  assert.ok(mixed.includes(Buffer.from('本文').toString('base64')));
  assert.ok(mixed.trimEnd().endsWith('--BB--'));
});
