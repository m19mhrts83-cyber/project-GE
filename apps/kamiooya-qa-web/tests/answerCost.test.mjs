import test from 'node:test';
import assert from 'node:assert/strict';
import {createProductionAdapter} from '../lib/raimoAuthAdapter.ts';
import {createRaimoAuthGateway} from '../lib/raimoAuthGateway.ts';
import {normalizeQuery,answerTier,cacheable,queryKey,fresh} from '../lib/answerCost.ts';

test('質問の正規化・モデルの使い分け・使い回せる答え', async () => {
  assert.equal(normalizeQuery('  火災保険　の 保険料？ '), '火災保険 の 保険料');
  assert.equal(await queryKey('火災保険の保険料？'), await queryKey('火災保険の保険料'));
  assert.notEqual(await queryKey('火災保険の保険料'), await queryKey('地震保険の保険料'));
  assert.equal(answerTier('火災保険の保険料を下げるには'), 'lite');
  assert.equal(answerTier('火災保険と地震保険の違いを詳しく'), 'standard');
  assert.equal(answerTier('あ'.repeat(121)), 'standard');
  assert.equal(cacheable('参照内で確証が取れないため、お答えすることができません。'), false);
  assert.equal(cacheable('参考情報から読み取れる留意点は次のとおりです。' + 'x'.repeat(50)), false);
  assert.equal(cacheable('補償の範囲を見直し、水災の要否を地域のハザードで判断し、複数社で見積もりを取ります。'), true);
  // 同じ日（日本時間）だけ。11/10 23:59 JST に作った答えは 11/11 0:01 JST には使わない
  const at = iso => Date.parse(iso);
  assert.equal(fresh({ created_at: '2026-11-10T00:30:00+09:00' }, at('2026-11-10T23:50:00+09:00')), true);
  assert.equal(fresh({ created_at: '2026-11-10T23:59:00+09:00' }, at('2026-11-11T00:01:00+09:00')), false);
  assert.equal(fresh({ created_at: '2026-11-09T12:00:00+09:00' }, at('2026-11-10T12:00:00+09:00')), false);
});

function fixture(stage) {
  const sessions = new Map(), jobs = new Map(), cache = new Map(), tasks = [], semanticBodies = [], appended = [];
  const c = { origin: 'https://app.example', raimoBase: 'https://app.example/miniAppApi/test', projectUrl: 'https://fixture.supabase.co', serviceKey: 'service-only', gatewaySecret: 'g'.repeat(40), proxySecret: 'p'.repeat(40) };
  const user = { id: 'one', email: 'owner@example.test', role: 'user', status: 'approved', password_hash: 'pw' };
  const transport = async (url, options = {}) => {
    const u = new URL(url), body = options.body ? JSON.parse(options.body) : {};
    if (u.pathname.endsWith('/rpc/raimo_auth_take_limit')) return Response.json(true);
    if (u.pathname.endsWith('/raimo_auth_sessions')) {
      const key = u.searchParams.get('token_hash')?.slice(3);
      if (options.method === 'POST') { sessions.set(body.token_hash, body); return new Response(null, { status: 201 }); }
      return Response.json(sessions.has(key) ? [sessions.get(key)] : []);
    }
    if (u.pathname.endsWith('/qa_feature_flags')) return Response.json([{ feature: 'cost_saving', stage, owner_ids: ['owner@example.test'] }]);
    if (u.pathname.endsWith('/qa_answer_cache')) {
      const key = (u.searchParams.get('query_hash') || '').slice(3);
      if (options.method === 'POST') { cache.set(body.query_hash, body); return new Response(null, { status: 201 }); }
      if (options.method === 'PATCH') { Object.assign(cache.get(key), body); return new Response(null, { status: 204 }); }
      return Response.json(cache.has(key) ? [cache.get(key)] : []);
    }
    if (u.pathname.endsWith('/rpc/qa_admit_answer_job')) { const job = { ...body.job, id: crypto.randomUUID(), status: 'running' }; jobs.set(job.id, job); return Response.json({ job, created: true }); }
    if (u.pathname.endsWith('/qa_answer_jobs')) {
      const id = u.searchParams.get('id')?.slice(3), job = jobs.get(id);
      if (options.method === 'PATCH') { Object.assign(job, body); return new Response(null, { status: 204 }); }
      return Response.json(job ? [job] : []);
    }
    if (url.startsWith(c.raimoBase)) {
      const path = u.pathname.slice('/miniAppApi/test'.length);
      if (path.startsWith('/internal/auth-user/')) return Response.json({ user });
      if (path === '/internal/read/chat-sessions/mine') return Response.json({ session: { user_id: 'one' } });
      if (path === '/semantic-search-config') return Response.json({ url: c.projectUrl + '/functions/v1/semantic-search', secret: 's'.repeat(43) });
      if (path === '/chat-sessions/mine/messages-append') { appended.push(body); return Response.json({ ok: true }); }
    }
    throw new Error('unexpected ' + url);
  };
  const adapter = createProductionAdapter(c, async (a, b) => a === b, async () => '', transport, {
    schedule: p => tasks.push(p),
    semantic: async request => { semanticBodies.push(await request.json()); return Response.json({ answer: '補償の範囲を見直し、水災の要否を地域のハザードで判断し、複数社で見積もりを取ります。', usedSources: '{}' }); }
  });
  const gateway = createRaimoAuthGateway(adapter.deps);
  const request = (path, body, token = '', method = 'POST') => gateway(new Request('https://gateway.example' + path, { method, headers: { Origin: c.origin, Authorization: 'Bearer ' + token }, ...(body !== undefined ? { body: JSON.stringify(body) } : {}) }));
  return { request, tasks, cache, semanticBodies, appended };
}
const ask = (f, token, n, query) => f.request('/chat-sessions/mine/answer-jobs', { request_id: `1111111${n}-1111-4111-8111-111111111111`, mode: 'semantic', query }, token);
async function login(f) { return (await (await f.request('/auth/login', { email: 'owner@example.test', password_hash: 'pw' })).json()).auth_token; }

test('スイッチの対象者: 軽いモデルで答え、同じ質問の2回目は AI を呼ばずに使い回す', async () => {
  const f = fixture('owner'), token = await login(f);
  await ask(f, token, 1, '火災保険の保険料を下げるには？'); await Promise.all(f.tasks);
  assert.equal(f.semanticBodies.length, 1);
  assert.equal(f.semanticBodies[0].answer_tier, 'lite');
  assert.equal(f.cache.size, 1);
  const r = await ask(f, token, 2, '火災保険の保険料を下げるには'); const job = await r.json(); await Promise.all(f.tasks);
  assert.equal(f.semanticBodies.length, 1); // 2回目は呼ばない
  const done = await (await f.request('/chat-sessions/mine/answer-jobs/' + job.job_id, undefined, token, 'GET')).json();
  assert.match(done.result.answer, /補償の範囲/);
  assert.equal([...f.cache.values()][0].hits, 1);
  assert.deepEqual(f.appended.map(m => m.role), ['user', 'assistant', 'user', 'assistant']);
});

test('スイッチがオフなら今までどおり（今のモデル・使い回しなし）', async () => {
  const f = fixture('off'), token = await login(f);
  await ask(f, token, 1, '火災保険の保険料を下げるには'); await Promise.all(f.tasks);
  await ask(f, token, 2, '火災保険の保険料を下げるには'); await Promise.all(f.tasks);
  assert.equal(f.semanticBodies.length, 2);
  assert.equal(f.semanticBodies[0].answer_tier, undefined);
  assert.equal(f.cache.size, 0);
});
