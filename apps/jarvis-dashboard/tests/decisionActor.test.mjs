import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';

function load(file) {
  const source = readFileSync(new URL(`../lib/${file}`, import.meta.url), 'utf8')
    .replace(/^import .*$/gm, '');
  const code = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText;
  const exports = {};
  vm.runInNewContext(code, { exports, Object, String, Promise });
  return exports;
}

const FAKE_ID = '00000000-aaaa-bbbb-cccc-000000000001';

test('getUser のIDが payload.actor_id に入る（メールは入れない）', async () => {
  const m = load('decisionActor.ts');
  const sb = { auth: { getUser: async () => ({ data: { user: { id: FAKE_ID, email: 'x@example.invalid' } } }) } };
  const p = m.withActorId({ a: 1 }, await m.currentActorId(sb));
  assert.equal(p.actor_id, FAKE_ID);
  assert.equal(p.a, 1);
  assert.ok(!JSON.stringify(p).includes('example.invalid'));
});

test('getUser が取れない・失敗する時は何も足さない', async () => {
  const m = load('decisionActor.ts');
  for (const getUser of [
    async () => ({ data: { user: null } }),
    async () => ({ data: null }),
    async () => { throw new Error('boom'); },
  ]) {
    const id = await m.currentActorId({ auth: { getUser } });
    assert.equal(id, null);
    const p = { a: 1 };
    assert.equal(m.withActorId(p, id), p);
  }
});

test('logOwnerDecision の actor は payload.actor に入り、無ければ従来どおり', () => {
  const m = load('ownerDecisionLog.ts');
  assert.deepEqual({ ...m.withActor({ k: 1 }, FAKE_ID) }, { k: 1, actor: FAKE_ID });
  assert.deepEqual({ ...m.withActor(undefined, FAKE_ID) }, { actor: FAKE_ID });
  const orig = { k: 1 };
  assert.equal(m.withActor(orig, null), orig);
  assert.equal(m.withActor(undefined, ''), undefined);
});
