import { test } from 'node:test';
import assert from 'node:assert/strict';
import { loadLib } from './load.mjs';

const c = loadLib('decisionContract');
const plain = (x) => JSON.parse(JSON.stringify(x));

const base = { surface: 'triage', action: 'skipped', source: 'loopware', targetType: 'triage_item', targetId: 'gha-cw-7790cf4' };

test('契約に揃えた1行には版・鍵・結果の区分が付く', () => {
  const n = c.normalizeDecision({ ...base, idemKey: 'dec-1', reasonTags: ['no_reply', 'no_reply', 'へんなタグ'] });
  assert.equal(n.ok, true);
  assert.equal(n.row.payload.v, 1);
  assert.equal(n.row.payload.idem_key, 'dec-1');
  assert.equal(n.row.payload.outcome, 'ng');
  assert.deepEqual(plain(n.row.payload.reason_tags), ['no_reply']);
  assert.deepEqual(plain(n.row.payload.reason_tags_unknown), ['へんなタグ']);
});

test('迷った・見ていないは NG に混ぜない', () => {
  assert.equal(c.outcomeOf('hesitated'), 'hesitate');
  assert.equal(c.outcomeOf('unseen'), 'none');
  assert.equal(c.outcomeOf('skipped'), 'ng');
  assert.equal(c.outcomeOf('meh'), 'note');
});

test('知らない surface / action / 入口は弾く', () => {
  assert.equal(c.normalizeDecision({ ...base, surface: 'nope' }).ok, false);
  assert.equal(c.normalizeDecision({ ...base, action: 'nope' }).ok, false);
  assert.equal(c.normalizeDecision({ ...base, source: 'fax' }).ok, false);
  assert.equal(c.normalizeDecision({ ...base, targetType: '' }).ok, false);
});

test('従来の細かい入口名は4つ＋script に寄せ、元の名前を残す', () => {
  const n = c.normalizeDecision({ ...base, surface: 'todoist_313', action: 'close', source: 'slack_button' });
  assert.equal(n.row.source, 'slack');
  assert.equal(n.row.payload.source_detail, 'slack_button');
  assert.equal(c.coarseSource('dashboard_or_script'), 'dashboard');
  assert.equal(c.coarseSource('app'), 'loopware');
  assert.equal(c.coarseSource('fax'), null);
});

test('鍵が無いときは同じ分の同じ判断を同じ鍵にする', () => {
  const at = new Date('2026-11-08T01:02:03Z');
  const a = c.normalizeDecision(base, at);
  const b = c.normalizeDecision(base, new Date('2026-11-08T01:02:59Z'));
  const d = c.normalizeDecision(base, new Date('2026-11-08T01:03:00Z'));
  assert.equal(a.idemKey, b.idemKey);
  assert.notEqual(a.idemKey, d.idemKey);
});

test('直しの割合と判断時間', () => {
  assert.equal(c.editRatio('abc', 'abc'), 0);
  assert.equal(c.editRatio(null, 'x'), null);
  assert.equal(c.editRatio('abcd', 'abcx'), 0.25);
  const n = c.normalizeDecision({
    ...base, action: 'sent', aiProposal: 'お世話になっております。', finalText: 'お世話になっております！',
    timing: { shown_at: '2026-11-08T00:00:00Z', decided_at: '2026-11-08T00:01:30Z', voice_sec: 12.4, read_ms: -5 },
  });
  assert.equal(n.row.edited, true);
  assert.equal(n.row.payload.decide_ms, 90000);
  assert.equal(n.row.payload.timing.voice_sec, 12);
  assert.equal(n.row.payload.timing.read_ms, undefined);
  // 開きっぱなし（6時間超）は数えない
  assert.equal(c.decideMs({ shown_at: '2026-11-08T00:00:00Z', decided_at: '2026-11-08T07:00:00Z' }), null);
});

test('声の区切りは「ここ／これ」に印を付ける', () => {
  const n = c.normalizeDecision({
    ...base, action: 'comment',
    voice: { segments: [{ target: '件名A', line: 2, text: 'ここは丁寧に' }, { target: '件名A', text: '問題なし' }, { text: '' }] },
  });
  const segs = plain(n.row.payload.voice.segments);
  assert.equal(segs.length, 2);
  assert.equal(segs[0].vague, true);
  assert.equal(segs[1].vague, undefined);
});

test('呼び出し側の payload より契約のキーが勝つ', () => {
  const n = c.normalizeDecision({ ...base, idemKey: 'k', payload: { v: 99, idem_key: 'x', extra: 1 } });
  assert.equal(n.row.payload.v, 1);
  assert.equal(n.row.payload.idem_key, 'k');
  assert.equal(n.row.payload.extra, 1);
});

test('今週の粒を数え、週は月曜0時（JST）から', () => {
  const t = c.tally([{ action: 'sent' }, { action: 'hesitated' }, { action: 'skipped', payload: { outcome: 'ng' } }, { action: 'unseen' }]);
  assert.deepEqual(plain(t), { take: 1, ng: 1, hesitate: 1, none: 1, later: 0, note: 0, total: 4 });
  // 2026-11-08 は日曜 → 週の始まりは 11/2(月) 0:00 JST = 11/1 15:00Z
  assert.equal(c.weekStartIso(new Date('2026-11-08T05:00:00Z')), '2026-11-01T15:00:00.000Z');
  assert.equal(c.weekStartIso(new Date('2026-11-01T15:00:00Z')), '2026-11-01T15:00:00.000Z');
});

test('618の確定判断は共通契約で受け付け、独自payloadを保持する', () => {
  const n = c.normalizeDecision({ ...base, surface: 'asset_618', action: 'rule_accept',
    source: 'script', employee: '618', targetType: 'asset618_decision', targetId: 'rule-1',
    payload: { asset_618: { owner_confirmed: true, targets: ['sbi_index'] } },
  });
  assert.equal(n.ok, true);
  assert.equal(n.row.surface, 'asset_618');
  assert.equal(n.row.payload.asset_618.owner_confirmed, true);
});
