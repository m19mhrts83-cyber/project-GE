import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const src = (p) => readFileSync(new URL(`../${p}`, import.meta.url), 'utf8');

// 外に届く操作の入口に、ボットを止める守りが残っていること（消えたら気づく）
const GUARDED = [
  'app/api/desk/reply/route.ts', // 返信の「送る」
  'app/api/desk/decide/route.ts', // 見送り・Todoist・回答不要
  'app/api/desk/next/route.ts', // 次の一手の ToDo・見送り
  'app/api/decide/route.ts', // 312/313 の判断（Todoist 反映）
  'app/api/cleanup/route.ts', // 313 まとめ判断（Todoist 反映）
  'app/api/week/route.ts', // 今週の9件の確定（Todoist 反映）
];

for (const p of GUARDED) {
  test(`ボットは止める: ${p}`, () => {
    assert.match(src(p), /botForbidden\(req\)/);
  });
}

test('Jarvis への送信・状態変更は、ボットなら呼ばない', () => {
  const s = src('lib/desk.ts');
  assert.equal((s.match(/actor === "bot"/g) || []).length, 2);
});

test('middleware は外から付けた actor を捨てて Cookie から付け直す', () => {
  const s = src('middleware.ts');
  assert.match(s, /clean\.delete\(ACTOR_HEADER\)/);
  assert.match(s, /clean\.set\(ACTOR_HEADER, actor\)/);
});

test('判断ログには actor を残す', () => {
  assert.match(src('lib/ownerDecisionLog.ts'), /actor/);
});
