import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync, readdirSync, statSync } from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';

const src = readFileSync(new URL('../lib/viewerRole.ts', import.meta.url), 'utf8');
const js = ts.transpileModule(src, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText;
const mod = { exports: {} };
vm.runInNewContext(js, { module: mod, exports: mod.exports });
const { isViewerUser, viewerMayRequest } = mod.exports;

test('app_metadata.role=viewer だけ viewer。user_metadata の自称は無効', () => {
  assert.equal(isViewerUser({ app_metadata: { role: 'viewer' } }), true);
  assert.equal(isViewerUser({ app_metadata: { role: ' Viewer ' } }), true);
  assert.equal(isViewerUser({ app_metadata: {}, user_metadata: { role: 'viewer' } }), false);
  assert.equal(isViewerUser(null), false);
  assert.equal(isViewerUser({}), false);
});

test('viewer は書き込みメソッドを全パスで拒否（サーバーアクション=POST・API 含む）', () => {
  for (const m of ['POST', 'PUT', 'PATCH', 'DELETE', 'post']) {
    for (const p of ['/', '/mail', '/api/slack/consult-action', '/api/g/t313/done/x', '/api/comm-intake', '/queue']) {
      assert.equal(viewerMayRequest(m, p), false, `${m} ${p}`);
    }
  }
});

test('viewer は読み取りとサインアウトだけ可', () => {
  for (const m of ['GET', 'HEAD', 'OPTIONS']) assert.equal(viewerMayRequest(m, '/mail'), true);
  assert.equal(viewerMayRequest('POST', '/auth/signout'), true);
  assert.equal(viewerMayRequest('DELETE', '/auth/signout'), false);
});

test('middleware は viewer 判定をバイパス分岐より前に置く', () => {
  const mw = readFileSync(new URL('../middleware.ts', import.meta.url), 'utf8');
  const gate = mw.indexOf('isViewerUser(user)');
  assert.ok(gate > 0 && mw.includes('status: 403'));
  assert.ok(gate < mw.indexOf('/api/quiet-edge/health/ingest'));
});

test('GET ハンドラは副作用を持たない前提: app/api 以外の route.ts は GET/POST を明示', () => {
  // 書き込み系 GET が増えたら viewer を通してしまう。session で動く GET route を列挙して固定する
  const found = [];
  (function walk(d) {
    for (const f of readdirSync(d)) {
      const p = `${d}/${f}`;
      if (statSync(p).isDirectory()) walk(p);
      else if (f === 'route.ts') found.push(p);
    }
  })(new URL('../app', import.meta.url).pathname);
  const sessionGet = found
    .filter((p) => /export (async )?function GET/.test(readFileSync(p, 'utf8')))
    .map((p) => p.split('/app/')[1])
    .filter((p) => !/^api\/(g|slack|todoist|line|flowforge|obsidian|advisor|inquiry|job-recovery|comm-intake|mac-watch|quiet-edge)/.test(p));
  assert.deepEqual(sessionGet.sort(), ['api/mail/[id]/image/route.ts', 'auth/callback/route.ts', 'go/loopware/route.ts']);
});

test('RLS migration: viewer を insert/update/delete で拒否し storage も対象', () => {
  const sql = readFileSync(new URL('../supabase/migrations/20261127_viewer_readonly_rls.sql', import.meta.url), 'utf8');
  assert.match(sql, /app_metadata.*role.*viewer/s);
  assert.match(sql, /as restrictive for insert/);
  assert.match(sql, /as restrictive for %s/);
  assert.match(sql, /storage\.objects/);
});
