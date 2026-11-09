import test from 'node:test';
import assert from 'node:assert/strict';
import { loadLib } from './load.mjs';

const d = loadLib('draftCore');

const join = (segs, ops) => segs.filter((s) => ops.includes(s.op)).map((s) => s.text).join('');

test('diffText: 前後を正しく復元できる', () => {
  const a = 'いつもお世話になっております。\n概算作業時間：〇時間\n以上です。\n';
  const b = 'いつもお世話になっております。\n作業時間は、ご報告した9時間に含まれています。\n以上です。\n';
  const segs = d.diffText(a, b);
  assert.equal(join(segs, ['eq', 'del']), a);
  assert.equal(join(segs, ['eq', 'ins']), b);
  // 変わらない1行目は丸ごと eq
  assert.equal(segs[0].op, 'eq');
  assert.ok(segs[0].text.startsWith('いつもお世話になっております。'));
});

test('diffText: 行の中は1文字ずつ（小さな直しが小さく見える）', () => {
  const segs = d.diffText('費用の抑制について\n', '使用量の削減について\n');
  const st = d.diffStats(segs);
  assert.ok(st.places >= 1 && st.places <= 3);
  assert.ok(segs.some((s) => s.op === 'eq' && s.text.includes('について')));
});

test('diffText: 同じなら差分なし', () => {
  const st = d.diffStats(d.diffText('同じ\n', '同じ\n'));
  assert.equal(st.places, 0);
});

test('nextLabel と currentVersion（戻した版は飛ばす）', () => {
  const vs = [{ label: 'v1' }, { label: 'v2' }, { label: 'v3', reverted: true }];
  assert.equal(d.nextLabel(vs), 'v4');
  assert.equal(d.currentVersion(vs).label, 'v2');
});

test('buildRevisePrompt: 箇所とダメ出しが入る', () => {
  const p = d.buildRevisePrompt({
    text: '本文', recipient: '今村さん', channel: 'chatwork', context: 'R211-001 数字を添える',
    comments: [{ quote: '概算', start: 0, end: 2, text: '数字を入れて', via: 'voice' }, { quote: '', start: null, end: null, text: '全体に短く', via: 'typed' }],
  });
  assert.match(p, /「概算」の箇所: 数字を入れて/);
  assert.match(p, /全体: 全体に短く/);
  assert.match(p, /R211-001/);
});

test('parseRevise: コードブロックつきでも読める・壊れていれば null', () => {
  const r = d.parseRevise('```json\n{"text":"直した","changes":[{"before":"a","after":"b","why":"1"}],"rule_hint":"短く"}\n```');
  assert.equal(r.text, '直した');
  assert.equal(r.changes.length, 1);
  assert.equal(r.ruleHint, '短く');
  assert.equal(d.parseRevise('だめ'), null);
  assert.equal(d.parseRevise('{"text":""}'), null);
});

test('commentsNote', () => {
  assert.equal(d.commentsNote([{ quote: 'ここ', text: '直す' }, { quote: '', text: '全体' }]), '「ここ」→ 直す / 全体');
});

test('paragraphs: 空行を飛ばし、元の位置を保つ', () => {
  const t = '一行目\n\n二行目です\n三行目';
  const ps = d.paragraphs(t);
  assert.equal(ps.length, 3);
  for (const p of ps) assert.equal(t.slice(p.start, p.end), p.text);
  assert.equal(ps[d.paragraphAt(ps, t.indexOf('二'))].text, '二行目です');
  assert.equal(d.paragraphAt(ps, 4), -1);
});
