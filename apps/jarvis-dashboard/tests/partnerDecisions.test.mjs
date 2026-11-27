import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';

function compile(file) {
  const source = readFileSync(new URL(`../lib/${file}`, import.meta.url), 'utf8');
  return ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText;
}
function load() {
  const blocks = {};
  vm.runInNewContext(compile('maDecisionBlocks.ts'), { exports: blocks, Date, Math, RegExp, Array, Object, Number, String });
  const exports = {};
  const require = (p) => {
    if (p === '@/lib/maDecisionBlocks') return blocks;
    throw new Error(p);
  };
  vm.runInNewContext(compile('partnerDecisions.ts'), { exports, require, Array, Object, Number, String, Map });
  return exports;
}

// 架空の送り手だけを使う
const rows = [
  { id: 1, decided_at: '2026-11-20T01:00:00Z', action: 'skipped', partner: 'テスト商事', payload: { partner_key: 'a@example.test', reason_tags: ['promo'] } },
  { id: 2, decided_at: '2026-11-22T01:00:00Z', action: 'todoist', partner: 'テスト商事', payload: { partner_key: 'a@example.test', reason_tags: ['research'] } },
  { id: 3, decided_at: '2026-11-23T01:00:00Z', action: 'skipped', partner: 'テスト商事（旧表記）', payload: { partner_key: 'a@example.test' } },
  { id: 4, decided_at: '2026-11-21T01:00:00Z', action: 'hesitated', partner: 'サンプル工務店', payload: {} },
  { id: 5, decided_at: '2026-11-21T02:00:00Z', action: 'sent', partner: 'サンプル工務店', payload: {} },
  { id: 6, decided_at: '2026-11-21T03:00:00Z', action: 'skipped', partner: 'ベンダー', payload: { slack_vr_action: { action: 'skip' } } },
  { id: 7, decided_at: '2026-11-21T04:00:00Z', action: 'skipped', partner: '', payload: {} },
];

test('送り手の識別子で束ね、無い行は名前で束ねる。sent・業者返信・鍵なしは数えない', () => {
  const m = load();
  const s = m.summarizeByPartner(rows);
  assert.equal(s.length, 2);
  assert.equal(s[0].key, 'a@example.test');
  assert.equal(s[0].total, 3);
  assert.equal(s[0].counts.skipped, 2);
  assert.equal(s[0].counts.todoist, 1);
  assert.equal(s[0].withReason, 2);
  assert.equal(s[0].name, 'テスト商事（旧表記）'); // 最新の判断の表記
  assert.equal(s[1].key, 'サンプル工務店');
  assert.equal(s[1].counts.hesitated, 1);
});

test('パートナー別に新しい順で引け、理由は押したタグだけ', () => {
  const m = load();
  const d = m.decisionsForPartner(rows, 'A@Example.test');
  assert.deepEqual(d.map((r) => r.id), [3, 2, 1]);
  assert.deepEqual(Array.from(m.reasonLabelsOf(d[1])), ['調べてから返信']);
  assert.deepEqual(Array.from(m.reasonLabelsOf(d[2])), ['宣伝・通知']);
  assert.deepEqual(Array.from(m.reasonLabelsOf(d[0])), []);
});
