import test from 'node:test';
import assert from 'node:assert/strict';
import { createRaimoAuthGateway } from '../lib/raimoAuthGateway.ts';
import { createHandler as attachments } from '../supabase/functions/community-attachments/index.ts';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

const origin = 'https://offline.example';
const req = (path, token = '', body, method = 'POST', requestOrigin = origin) => new Request('https://gateway.example' + path, {
  method, headers: { Origin: requestOrigin, Authorization: 'Bearer ' + token }, ...(body === undefined ? {} : { body: JSON.stringify(body) }),
});
function setup() {
  const members = new Map([
    ['u', { id: 'u', email: 'u@example.test', role: 'user', status: 'approved', authVersion: '1', password_hash: 'never-return', secret: 'never-return' }],
    ['a', { id: 'a', email: 'a@example.test', role: 'admin', status: 'approved', authVersion: '1' }],
    ['m', { id: 'm', email: 'm@example.test', role: 'master_admin', status: 'approved', authVersion: '1' }],
  ]);
  const saved = new Map(), calls = [];
  let clock = 1800000000000, loginAllowed = true;
  const d = { origin, now: () => clock,
    authenticate: async (email, password) => password === 'fixture-password' ? [...members.values()].find(u => u.email === email) || null : null,
    member: async uid => members.get(uid) || null,
    sessions: { get: async t => saved.get(t) || null, put: async (t,s) => saved.set(t,s), delete: async t => saved.delete(t) },
    allowLogin: async () => loginAllowed,
    chatOwner: async id => id === 'mine' ? 'u' : 'other',
    forward: async (method, path, body) => { calls.push({ method, path, body }); return path.startsWith('/admin/users') && method === 'GET' ? { users: [...members.values()] } : { ok: true }; },
    attachmentSession: async uid => ({ token: 'attachment-for-' + uid }),
  };
  const handler = createRaimoAuthGateway(d);
  const login = async (uid = 'u') => {
    const r = await handler(req('/auth/login', '', { email: uid + '@example.test', password_hash: 'fixture-password' }));
    assert.equal(r.status, 200); return (await r.json()).auth_token;
  };
  return { d, handler, login, members, saved, calls, advance: () => clock += 28800001, throttle: () => loginAllowed = false };
}
test('login returns only public identity plus an opaque session; rejects forged/stale sessions', async () => {
  const s = setup(); const token = await s.login();
  assert.match(token, /^[a-f0-9]{64}$/);
  assert.equal(JSON.stringify([...s.saved.values()]).includes('never-return'), false);
  const res = await s.handler(req('/auth/login', '', { email: 'U@EXAMPLE.TEST', password_hash: 'fixture-password' }));
  const body = await res.json();
  assert.deepEqual(Object.keys(body.user).sort(), ['email','id','role','status']);
  assert.equal((await s.handler(req('/comments', 'f'.repeat(64), undefined, 'GET'))).status, 401);
  s.advance(); assert.equal((await s.handler(req('/comments', token, undefined, 'GET'))).status, 401);
});
test('wrong credentials, throttling, pending and unknown roles never create sessions', async () => {
  const s = setup();
  assert.equal((await s.handler(req('/auth/login', '', { email: 'u@example.test', password_hash: 'wrong' }))).status, 401);
  for (const state of [{ status: 'pending' }, { role: 'invented', status: 'approved' }]) {
    Object.assign(s.members.get('u'), state);
    assert.equal((await s.handler(req('/auth/login', '', { email: 'u@example.test', password_hash: 'fixture-password' }))).status, 401);
  }
  assert.equal(s.saved.size, 0);
  s.throttle(); assert.equal((await s.handler(req('/auth/login', '', { email: 'u@example.test', password_hash: 'x' }))).status, 429);
});
test('current membership, role and credential version are checked on every request', async () => {
  for (const change of [{status:'withdrawn'}, {status:'pending'}, {role:'unknown'}, {authVersion:'2'}]) {
    const s = setup(), token = await s.login(); Object.assign(s.members.get('u'), change);
    assert.equal((await s.handler(req('/comments', token, undefined, 'GET'))).status, 403);
    assert.equal(s.calls.length, 0);
  }
  const s = setup(), token = await s.login('a'); s.members.get('a').role = 'user';
  assert.equal((await s.handler(req('/admin/users', token, undefined, 'GET'))).status, 403);
});
test('browser user and role claims cannot authorize admin access; lists exclude credential fields', async () => {
  const s = setup(), user = await s.login(), admin = await s.login('a');
  assert.equal((await s.handler(req('/admin/users/u/approve', user, {role:'master_admin', actor_user_id:'m'}, 'PUT'))).status, 403);
  assert.equal((await s.handler(req('/admin/users/u/approve', admin, {}, 'PUT'))).status, 403);
  const result = await s.handler(req('/admin/users', admin, undefined, 'GET'));
  assert.equal(result.status, 200);
  assert.equal(JSON.stringify(await result.json()).includes('never-return'), false);
});
test('chat ownership is enforced even for staff and body actors are replaced', async () => {
  const s = setup(), token = await s.login();
  assert.equal((await s.handler(req('/chat-sessions/mine/messages', token, {actor_user_id:'m', user_id:'other', __gateway_secret:'fake', secret:'fake', message:'hello'}))).status, 200);
  assert.deepEqual(s.calls[0].body, {actor_user_id:'u', message:'hello'});
  for (const [path, method] of [['/chat-sessions/theirs','GET'], ['/users/other/chat-sessions','GET'], ['/chat-sessions/missing/messages','POST']]) {
    assert.equal((await s.handler(req(path, token, method === 'GET' ? undefined : {}, method))).status, 403);
  }
  assert.equal((await s.handler(req('/chat-sessions/mine', await s.login('a'), undefined, 'GET'))).status, 403);
});
test('logout revokes; reset/bootstrap/notification and unreviewed operations remain closed', async () => {
  const s = setup(), token = await s.login('m');
  for (const path of ['/auth/reset-password','/auth/forgot-password/issue','/admin/bootstrap-master','/semantic-search-config']) {
    assert.equal((await s.handler(req(path, token, {}))).status, 403);
  }
  assert.equal((await s.handler(req('/auth/logout', token, {}))).status, 200);
  assert.equal((await s.handler(req('/comments', token, undefined, 'GET'))).status, 401);
});
test('malformed input, wrong origin and upstream failure fail closed without detail leakage', async () => {
  const s = setup(), token = await s.login();
  assert.equal((await s.handler(req('/comments', token, undefined, 'GET', 'https://wrong.example'))).status, 403);
  assert.equal((await s.handler(req('/comments?actor_user_id=m', token, undefined, 'GET'))).status, 400);
  assert.equal((await s.handler(req('/auth/login', '', []))).status, 400);
  s.d.forward = async () => { throw new Error('sensitive-upstream-body'); };
  const response = await s.handler(req('/comments', token, undefined, 'GET'));
  assert.equal(response.status, 503); assert.equal((await response.text()).includes('sensitive'), false);
});
test('offline functional flow: login -> attachment session -> metadata -> signed PDF -> logout', async () => {
  const s = setup(); const now = s.d.now();
  const cfg = { origin, projectUrl:'https://storage.example', serviceKey:'fixture-service-only', memberReadsEnabled:true, requireParentSession:true,
    proxySecret:'p'.repeat(40), sessionSecret:'s'.repeat(40), raimoOrigin:origin, statusUrl:origin+'/member' };
  const aid = 'a'.repeat(64), path = 'comments/12/'+'b'.repeat(64)+'.pdf';
  const edge = attachments(cfg, async (url, opts) => {
    if (url === cfg.statusUrl) {
      const input=JSON.parse(opts.body), u=s.members.get(input.user_id);
      let active=false;
      for (const [token,session] of s.saved) {
        const ref=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(token))),b=>b.toString(16).padStart(2,'0')).join('');
        if (input.session_ref===ref && session.uid===u?.id && session.expires>s.d.now() && session.authVersion===u?.authVersion) active=true;
      }
      return Response.json({user_id:u?.id,status:u?.status,role:u?.role,session_active:active});
    }
    if (url.includes('/rest/v1/')) return Response.json([{id:aid, bucket:'community-attachments',storage_path:path}]);
    assert.ok(url.includes('/storage/v1/object/sign/')); return Response.json({signedURL:'/object/sign/community-attachments/'+path+'?token=fixture'});
  }, () => now);
  const edgeRequest = (body, token) => new Request('https://edge.example', {method:'POST', headers:{Authorization:'Bearer '+token, Origin:origin}, body:JSON.stringify(body)});
  s.d.attachmentSession = async (uid,parent) => {
    const r = await edge(edgeRequest({operation:'session',user_id:uid,parent_session:parent},cfg.proxySecret)); assert.equal(r.status,200); return r.json();
  };
  const login = await s.login();
  const minted = await s.handler(req('/auth/attachment-session',login,{user_id:'m',password_hash:'ignored'}));
  const {token} = await minted.json();
  const indexed = await edge(edgeRequest({operation:'index'},token)); assert.equal(indexed.status,200);
  const opened = await edge(edgeRequest({operation:'open',attachment_id:aid},token)); assert.equal(opened.status,200);
  assert.ok((await opened.json()).url.includes(path));
  s.members.get('u').status='withdrawn'; assert.equal((await edge(edgeRequest({operation:'open',attachment_id:aid},token))).status,403);
  s.members.get('u').status='approved';
  // Production still has the hard hold, even if a valid session exists.
  const held = attachments({...cfg,memberReadsEnabled:false},async()=>assert.fail('no upstream'),()=>now);
  assert.equal((await held(edgeRequest({operation:'open',attachment_id:aid},token))).status,503);
  assert.equal((await s.handler(req('/auth/logout',login,{}))).status,200);
  assert.equal((await edge(edgeRequest({operation:'open',attachment_id:aid},token))).status,401);
  assert.equal((await edge(edgeRequest({operation:'session',user_id:'u'},cfg.proxySecret))).status,401);
});
test('concurrent sessions remain bound to the authenticated user', async () => {
  const s=setup();
  const tokens = await Promise.all(['u','a','m'].map(id=>s.login(id)));
  assert.equal(new Set(tokens).size,3);
  const results = await Promise.all(tokens.map(token=>s.handler(req('/auth/attachment-session',token,{user_id:'spoof'})).then(r=>r.json())));
  assert.deepEqual(results.map(r=>r.token), ['attachment-for-u','attachment-for-a','attachment-for-m']);
});
for (const path of [new URL('../public/raimo/app.js',import.meta.url),new URL('../../../215_kamiooya/C1_cursor/1c_神・大家さん倶楽部_AI推進/神・大家さん倶楽部情報Q&Aチャットボット/app.js',import.meta.url)]) {
  test('actual frontend login/API/logout with offline gateway: '+path.pathname,async()=>{
    const s=setup();
    const fields={loginEmail:{value:'u@example.test'},loginPassword:{value:'fixture-password'}};
    const app=vm.runInNewContext(readFileSync(path,'utf8')+'\nApp;',{
      document:{addEventListener(){},getElementById:id=>fields[id]},window:{},console,URL,
      fetch:async(url,opts)=>s.handler(new Request(url,{...opts,headers:{...opts.headers,Origin:origin}})),
    });
    assert.equal(app.authGatewayBase,''); // opt-in is never activated in the shipped bundle.
    app.authGatewayBase='https://gateway.example';
    app.setButtonLoading=()=>{};app.setLoading=()=>{};app.showToast=()=>{};app.afterLogin=()=>{};app.showAuthView=()=>{};
    app.initializeAttachments=async()=>{};
    app.elements.loginForm={reset(){}};app.elements.registerForm={reset(){}};
    await app.handleLogin({preventDefault(){}});
    assert.equal(app.state.currentUser.id,'u'); assert.match(app.state.authToken,/^[0-9a-f]{64}$/);
    assert.equal(JSON.stringify(app.state).includes('fixture-password'),false);
    await app.apiClient('GET','/comments');assert.equal(s.calls.length,1);
    const token=app.state.authToken;app.logout();
    await new Promise(resolve=>setImmediate(resolve));
    assert.equal(app.state.authToken,'');assert.equal(s.saved.has(token),false);
  });
}
