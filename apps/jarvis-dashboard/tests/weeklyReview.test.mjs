import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';

function compile(rel, requireMap = {}) {
  const source = readFileSync(new URL(rel, import.meta.url), 'utf8');
  const code = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText;
  const exports = {};
  const require = (name) => {
    if (name in requireMap) return requireMap[name];
    throw new Error(`unexpected require ${name}`);
  };
  vm.runInNewContext(code, { exports, require, Date, Math, RegExp, Array, Object, Number, String, JSON, Map, Set, Boolean });
  return exports;
}

function load() {
  const contract = compile('../lib/decisionContract.ts');
  return compile('../lib/weeklyReview.ts', { '@/lib/decisionContract': contract });
}

const rows = [
  { id: 1, decided_at: '2026-11-08T01:00:00Z', surface: 'triage', action: 'sent', lane: 'partner', subject: 'エアコン', ai_proposal: 'お世話になっております。確認します。', final_text: 'お世話になっております。本日中に確認して折り返します。', edited: true, payload: { outcome: 'take', edit_ratio: 0.45 } },
  { id: 2, decided_at: '2026-11-08T02:00:00Z', surface: 'triage', action: 'skipped', lane: 'general', subject: 'セール', payload: { outcome: 'ng', reason_tags: ['promo'] } },
  { id: 3, decided_at: '2026-11-08T03:00:00Z', surface: 'triage', action: 'skipped', lane: 'general', subject: 'セール2', payload: { reason_tags: ['promo', 'no_reply'] } },
  { id: 4, decided_at: '2026-11-08T04:00:00Z', surface: 'triage_miss', action: 'wrong', lane: 'partner', subject: '請求', note: '要対応だった', payload: {} },
  { id: 5, decided_at: '2026-11-08T05:00:00Z', surface: 'mail_send', action: 'meh', subject: '返信', payload: { applied_rules: ['R116-1'] } },
  { id: 6, decided_at: '2026-11-08T06:00:00Z', surface: 'triage', action: 'sent', lane: 'general', ai_proposal: 'a', final_text: 'a', edited: false, payload: { applied_rules: ['R116-1'] } },
];

test('件数・直して送った・見落としを数える', () => {
  const m = load();
  const s = m.stats(rows);
  assert.equal(s.total, 6);
  assert.equal(s.take, 2);
  assert.equal(s.ng, 3); // 見落とし（wrong）も契約どおり NG に数える
  assert.equal(s.sent, 2);
  assert.equal(s.edited, 1);
  assert.equal(s.misses, 1);
});

test('社員の割り当てと社員別の表', () => {
  const m = load();
  assert.equal(m.employeeOf(rows[0]), '111');
  assert.equal(m.employeeOf(rows[1]), '116');
  assert.equal(m.employeeOf(rows[4]), '211');
  const e = m.byEmployee(rows, []);
  assert.equal(e[0].employee, '116');
  assert.equal(e[0].now.total, 3);
});

test('理由タグの多い順', () => {
  const m = load();
  const r = m.reasonCounts(rows);
  assert.equal(JSON.stringify(r.map((x) => [x.tag, x.n])), JSON.stringify([['promo', 2], ['no_reply', 1]]));
});

test('見ておきたい判断: 見落とし・大きな直し・いまいち（新しい順）', () => {
  const m = load();
  const t = m.troubles(rows);
  assert.equal(JSON.stringify(t.map((x) => x.kind)), JSON.stringify(['いまいち', '見落とし', '大きく直した']));
  assert.match(t[2].detail, /45%/);
});

test('候補の読み込みと判断済みの見分け', () => {
  const m = load();
  const v = JSON.stringify({ week: '2026-W45', at: '2026-11-07T21:00:00+09:00', candidates: [
    { id: 'C1234abcd', kind: 'hide', employee: '116', key: 'a@x.jp', rule_line: 'hide | from:a@x.jp', text: 't', why: 'w', evidence: [2, 3], status: 'hypothesis' },
    { id: 'bad', kind: 'hide' },
  ] });
  const c = m.parseCandidates(v);
  assert.equal(c.candidates.length, 1);
  assert.equal(m.parseCandidates('{broken').candidates.length, 0);
  const st = m.candidateStates([
    { id: 9, decided_at: '2026-11-08T00:00:00Z', surface: 'rule_review', action: 'comment', note: '請求書だけ', payload: { candidate_id: 'C1234abcd' } },
    { id: 10, decided_at: '2026-11-08T01:00:00Z', surface: 'rule_review', action: 'rule_once', payload: { candidate_id: 'C1234abcd' } },
  ]);
  assert.equal(st.get('C1234abcd').decided, 'rule_once');
  assert.equal(JSON.stringify(st.get('C1234abcd').comments), JSON.stringify(['請求書だけ']));
  assert.equal(m.isStale('2026-11-07T21:00:00+09:00', new Date('2026-11-09T12:00:00+09:00')), false);
  assert.equal(m.isStale('2026-10-25T21:00:00+09:00', new Date('2026-11-09T12:00:00+09:00')), true);
  assert.equal(m.isStale(null), true);
});

test('ルールの効き・前週比の表記', () => {
  const m = load();
  const e = m.ruleEffects(rows);
  assert.equal(e.length, 1);
  assert.equal(e[0].rule, 'R116-1');
  assert.equal(e[0].take, 1);
  assert.equal(e[0].other, 1);
  assert.equal(m.delta(5, 3), '+2');
  assert.equal(m.delta(1, 3), '-2');
  assert.equal(m.delta(2, 2), '±0');
  assert.equal(m.pct(m.rate(1, 4)), '25%');
  assert.equal(m.pct(m.rate(1, 0)), '—');
});
