import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';

function load() {
  const source = readFileSync(new URL('../lib/maDecisionBlocks.ts', import.meta.url), 'utf8');
  const code = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText;
  const exports = {};
  vm.runInNewContext(code, { exports, Date, Math, RegExp, Array, Object, Number, String });
  return exports;
}

test('理由タグと送り手確認のボタン値を往復できる', () => {
  const m = load();
  assert.deepEqual({ ...m.parseMaReasonValue(m.maReasonValue('hesitate', 'gha-cw-7790cf4')) }, { tag: 'hesitate', id: 'gha-cw-7790cf4' });
  assert.deepEqual({ ...m.parseMaMuteValue(m.maMuteValue('partner', 'abc-123456')) }, { choice: 'partner', id: 'abc-123456' });
  assert.equal(m.parseMaReasonValue('mar:bad:abc-123456'), null);
  assert.equal(m.parseMaReasonValue('ma:skip:abc-123456'), null);
  assert.equal(m.parseMaMuteValue('mam:always:abc-123456'), null);
});

test('週の始まりは月曜 0:00 JST', () => {
  const m = load();
  // 2026-11-08 は日曜 → 11/2(月) 0:00 JST = 11/1 15:00Z
  assert.equal(m.weekStartIso(new Date('2026-11-08T09:00:00Z')), '2026-11-01T15:00:00.000Z');
  // 月曜 0:30 JST は当日が週頭
  assert.equal(m.weekStartIso(new Date('2026-11-08T15:30:00Z')), '2026-11-08T15:00:00.000Z');
});

test('下書きからの直し具合', () => {
  const m = load();
  assert.equal(m.editRatio('', 'x'), null);
  assert.equal(m.editRatio('お世話になっております。', 'お世話になっております。'), 0);
  assert.equal(m.editLabel(m.editRatio('お世話になっております。承知しました。', 'お世話になっております。承知いたしました。')), '少し直した');
  assert.equal(m.editLabel(m.editRatio('はい', 'まったく別の長い文章に書き換えました')), '書き直した');
});

test('見送り直後は理由タグを出し、押した後は1行に縮む', () => {
  const m = load();
  const first = m.maSkipFollowupBlocks({ id: 'abc-123456', who: '山田', weekCount: 12 });
  const txt = JSON.stringify(first);
  assert.match(txt, /今週 12 件/);
  assert.match(txt, /mar:promo:abc-123456/);
  assert.match(txt, /mar:hesitate:abc-123456/);
  assert.match(txt, /押さなくても進めます/);
  assert.doesNotMatch(txt, /mam:/);

  const tagged = JSON.stringify(m.maSkipFollowupBlocks({ id: 'abc-123456', who: '山田', weekCount: 13, tagged: 'hesitate' }));
  assert.match(tagged, /迷ったので見送り/);
  assert.doesNotMatch(tagged, /mar:/);
});

test('しきい値に届いたら「次からも？」を出し、答えたら結果だけ残す', () => {
  const m = load();
  const ask = JSON.stringify(m.maSkipFollowupBlocks({ id: 'abc-123456', who: 'x', weekCount: null, askMute: { skips: 2 } }));
  assert.match(ask, /2 回目/);
  assert.match(ask, /mam:once:abc-123456/);
  assert.match(ask, /mam:partner:abc-123456/);
  assert.match(ask, /✓ 判断ログに記録"/);

  const done = JSON.stringify(m.maSkipFollowupBlocks({ id: 'abc-123456', who: 'x', weekCount: 3, tagged: 'promo', muteDone: 'partner' }));
  assert.match(done, /次から出しません/);
  assert.doesNotMatch(done, /mam:/);
  assert.match(done, /理由: 宣伝・通知/);
});
