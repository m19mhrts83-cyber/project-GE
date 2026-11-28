import test from 'node:test';
import assert from 'node:assert/strict';
import { createHandler, issueSession, sessionUser } from '../supabase/functions/community-attachments/index.ts';

const cfg = { projectUrl: 'https://example.supabase.co', serviceKey: 'server-only-key',
  memberReadsEnabled: true,
  proxySecret: 'proxy-secret-'.repeat(4), sessionSecret: 'session-secret-'.repeat(4),
  raimoOrigin: 'https://app.example', statusUrl: 'https://app.example/status' };
const now = 1800000000000;
const id = 'a'.repeat(64);
const row = { id, bucket: 'community-attachments', storage_path: 'comments/12/' + 'b'.repeat(64) + '.pdf' };
const response = (obj, status = 200) => new Response(JSON.stringify(obj), { status });
const request = (body, token = '', origin = cfg.raimoOrigin) => new Request('https://edge.example', {
  method: 'POST', headers: { Authorization: 'Bearer ' + token, 'Content-Type': 'application/json', ...(origin ? { Origin: origin } : {}) },
  body: JSON.stringify(body),
});

test('security hold blocks new and previously issued sessions without upstream reads', async () => {
  const handler = createHandler({ ...cfg, memberReadsEnabled: false }, async () => assert.fail('must not fetch'), () => now);
  const token = await issueSession('12', cfg.sessionSecret, now);
  for (const operation of ['session', 'index', 'list', 'open']) {
    const res = await handler(request({ operation, user_id: '12', attachment_id: id }, operation === 'session' ? cfg.proxySecret : token));
    assert.equal(res.status, 503);
    assert.equal((await res.json()).error, 'attachments_temporarily_unavailable');
  }
});

test('session rejects forgery, expiry and altered user id', async () => {
  const token = await issueSession('12', cfg.sessionSecret, now);
  assert.equal(await sessionUser(token, cfg.sessionSecret, now), '12');
  assert.equal(await sessionUser(token + 'x', cfg.sessionSecret, now), null);
  assert.equal(await sessionUser(token, cfg.sessionSecret, now + 28800001), null);
  assert.equal(await sessionUser(await issueSession('13', 'wrong-key', now), cfg.sessionSecret, now), null);
});

test('only Raimo backend may mint a session', async () => {
  const handler = createHandler(cfg, async () => assert.fail('must not fetch'), () => now);
  assert.equal((await handler(request({ operation: 'session', user_id: '12' }, 'browser'))).status, 401);
  const res = await handler(request({ operation: 'session', user_id: '12' }, cfg.proxySecret, null));
  assert.equal(res.status, 200);
  assert.equal(await sessionUser((await res.json()).token, cfg.sessionSecret, now), '12');
});

test('current membership is rechecked and browser user id is ignored', async () => {
  let status = 'approved'; const users = [];
  const handler = createHandler(cfg, async (url, options) => {
    if (url === cfg.statusUrl) { users.push(JSON.parse(options.body).user_id); return response({ user_id: '12', status, role: 'user' }); }
    if (url.includes('/rest/v1/')) return response([row]);
    assert.ok(url.endsWith(row.storage_path));
    return response({ signedURL: '/object/sign/community-attachments/' + row.storage_path + '?token=temporary' });
  }, () => now);
  const token = await issueSession('12', cfg.sessionSecret, now);
  assert.equal((await handler(request({ operation: 'open', attachment_id: id, user_id: 'another-member' }, token))).status, 200);
  status = 'withdrawn';
  assert.equal((await handler(request({ operation: 'open', attachment_id: id }, token))).status, 403);
  assert.deepEqual(users, ['12', '12']);
});

test('unapproved, missing and unknown-role members cannot read metadata', async () => {
  for (const member of [ { user_id: '12', status: 'pending', role: 'user' }, { user_id: '12', status: 'approved', role: 'unknown' }, { user_id: 'different', status: 'approved', role: 'admin' } ]) {
    const handler = createHandler(cfg, async url => {
      assert.equal(url, cfg.statusUrl); return response(member);
    }, () => now);
    assert.equal((await handler(request({ operation: 'index' }, await issueSession('12', cfg.sessionSecret, now)))).status, 403);
  }
});

test('signed URL is generated only from validated metadata and is never cached', async () => {
  let stored = row;
  const handler = createHandler(cfg, async url => {
    if (url === cfg.statusUrl) return response({ user_id: '12', status: 'approved', role: 'master_admin' });
    if (url.includes('/rest/v1/')) return response([stored]);
    return response({ signedURL: '/object/sign/community-attachments/' + row.storage_path + '?token=temporary' });
  }, () => now);
  const token = await issueSession('12', cfg.sessionSecret, now);
  const res = await handler(request({ operation: 'open', attachment_id: id, storage_path: '../private' }, token));
  assert.equal(res.headers.get('cache-control'), 'no-store');
  assert.ok((await res.json()).url.startsWith(cfg.projectUrl + '/storage/v1/object/sign/community-attachments/comments/12/'));
  stored = { ...row, bucket: 'private-other-bucket' };
  assert.equal((await handler(request({ operation: 'open', attachment_id: id }, token))).status, 500);
});

test('10 simultaneous users remain isolated', async () => {
  const checked = [];
  const handler = createHandler(cfg, async (url, options) => {
    if (url === cfg.statusUrl) {
      const uid = JSON.parse(options.body).user_id; checked.push(uid);
      await new Promise(resolve => setTimeout(resolve, Number(uid) % 3));
      return response({ user_id: uid, status: 'approved', role: 'user' });
    }
    return response([]);
  }, () => now);
  const results = await Promise.all(Array.from({ length: 10 }, async (_, i) => {
    const uid = String(i + 1);
    return handler(request({ operation: 'index', user_id: 'spoof' }, await issueSession(uid, cfg.sessionSecret, now)));
  }));
  assert.ok(results.every(r => r.status === 200));
  assert.deepEqual(checked.sort(), Array.from({ length: 10 }, (_, i) => String(i + 1)).sort());
});

test('wrong origins and unauthenticated requests cannot call upstream', async () => {
  const handler = createHandler(cfg, async () => assert.fail('must not call upstream'), () => now);
  assert.equal((await handler(request({ operation: 'index' }, '', 'https://attacker.example'))).status, 403);
  assert.equal((await handler(request({ operation: 'index' }))).status, 401);
});

test('LINE delivery uses exact source IDs, bounded pages and only validated private objects', async () => {
  let stored={id,bucket:'openchat-attachments',storage_path:'objects/'+'c'.repeat(64)};
  const calls=[];
  const handler=createHandler(cfg,async(url,options)=>{
    if(url===cfg.statusUrl)return response({user_id:'12',status:'approved',role:'user'});
    calls.push(new URL(url));
    if(url.includes('/rest/v1/'))return response([stored]);
    assert.equal(JSON.parse(options.body).expiresIn,60);
    return response({signedURL:'/object/sign/openchat-attachments/'+stored.storage_path+'?token=temporary'});
  },()=>now);
  const token=await issueSession('12',cfg.sessionSecret,now);
  let res=await handler(request({operation:'list',source:'openchat',source_log_id:'oc_'+id},token));
  assert.equal(res.status,200);
  const meta=calls.find(u=>u.pathname==='/rest/v1/openchat_member_attachments');
  assert.equal(meta.searchParams.get('source_log_id'),'eq.oc_'+id);
  assert.ok(meta.searchParams.get('select').includes('source_log_id'));
  res=await handler(request({operation:'open',source:'openchat',attachment_id:id,storage_path:'../other'},token));
  assert.equal(res.status,200);assert.match((await res.json()).url,/\/openchat-attachments\/objects\//);
  stored={...stored,bucket:'community-attachments'};
  assert.equal((await handler(request({operation:'open',source:'openchat',attachment_id:id},token))).status,500);
  stored={...stored,bucket:'openchat-attachments',storage_path:'objects/../outside'};
  assert.equal((await handler(request({operation:'open',source:'openchat',attachment_id:id},token))).status,500);
  assert.equal((await handler(request({operation:'list',source:'openchat',source_log_id:'oc_123'},token))).status,400);
  assert.equal((await handler(request({operation:'index',source:'arbitrary-table'},token))).status,400);
});

test('LINE attachment delivery rechecks every role and its active parent login',async()=>{
  const parent='d'.repeat(64), token=await issueSession('12',cfg.sessionSecret,now,parent);
  for(const [status,role,active,expected] of [
    ['approved','user',true,200],['approved','admin',true,200],['approved','master_admin',true,200],
    ['pending','user',true,403],['withdrawn','user',true,403],['approved','unknown',true,403],
    ['approved','user',false,401]
  ]){
    const handler=createHandler({...cfg,requireParentSession:true},async(url,options)=>{
      if(url===cfg.statusUrl){assert.equal(JSON.parse(options.body).session_ref,parent);return response({user_id:'12',status,role,session_active:active});}
      return response([]);
    },()=>now);
    assert.equal((await handler(request({operation:'index',source:'openchat',user_id:'another'},token))).status,expected);
    assert.equal((await handler(request({operation:'index',source:'openchat'},''))).status,401);
  }
});

// 見られる人を限るオプチャ（lib/openchatAccess.ts）は、添付の窓口でも同じ判定で隠す（2026-11-28）。
test('restricted LINE rooms are hidden from attachment index, list and open unless the switch allows the viewer', async () => {
  const open = { id, source_log_id: 'oc_' + id, original_name: 'a.pdf', bucket: 'openchat-attachments', storage_path: 'objects/' + 'c'.repeat(64), route_id: 'room_x', chat_title: '一般の部屋', chat_name: '一般の部屋' };
  const limited = { ...open, id: 'e'.repeat(64), source_log_id: 'oc_' + 'e'.repeat(64), route_id: '23_saisei_ap_ms_challenge_g', chat_title: '23再生AP/MS 限定', chat_name: '23再生AP/MS 限定' };
  const byTitle = { ...limited, id: 'f'.repeat(64), route_id: 'attachment', chat_title: '23再生AP/MS チャレンジ' };
  const run = async ({ flags, flagsOk = true, email = 'member@example.com', role = 'user' }, body) => {
    const handler = createHandler(cfg, async url => {
      if (url === cfg.statusUrl) return response({ user_id: '12', status: 'approved', role, email });
      const u = new URL(url);
      if (u.pathname === '/rest/v1/qa_feature_flags') return flagsOk ? response(flags) : response({ message: 'down' }, 500);
      if (u.pathname === '/rest/v1/openchat_member_attachments') {
        assert.match(u.searchParams.get('select'), /route_id,chat_title,chat_name/);
        const all = [open, limited, byTitle];
        const idFilter = u.searchParams.get('id');
        return response(idFilter ? all.filter(r => 'eq.' + r.id === idFilter) : all);
      }
      return response({ signedURL: '/object/sign/openchat-attachments/' + open.storage_path + '?token=t' });
    }, () => now);
    return handler(request({ source: 'openchat', ...body }, await issueSession('12', cfg.sessionSecret, now)));
  };
  const ids = async res => (await res.json()).attachments.map(r => r.id);
  const owner = [{ feature: 'openchat_23', stage: 'owner', owner_ids: ['owner@example.com'] }];
  // 会員: 限定の部屋（route_id でも題名でも）は一覧に出ず、開けない
  for (const op of ['index', 'list']) {
    const res = await run({ flags: owner }, { operation: op, source_log_id: 'oc_' + id });
    assert.equal(res.status, 200);
    assert.deepEqual(await ids(res), [id]);
  }
  assert.equal((await run({ flags: owner }, { operation: 'open', attachment_id: limited.id })).status, 404);
  assert.equal((await run({ flags: owner }, { operation: 'open', attachment_id: byTitle.id })).status, 404);
  assert.equal((await run({ flags: owner }, { operation: 'open', attachment_id: id })).status, 200);
  // 判定に使った部屋の情報は返さない
  const listed = (await (await run({ flags: owner }, { operation: 'index' })).json()).attachments[0];
  assert.equal('route_id' in listed || 'chat_title' in listed || 'chat_name' in listed, false);
  // 名指しの本人（メール）・会員全員に出す段階では見える
  assert.deepEqual(await ids(await run({ flags: owner, email: 'Owner@example.com' }, { operation: 'index' })), [id, limited.id, byTitle.id]);
  assert.equal((await run({ flags: owner, email: 'owner@example.com' }, { operation: 'open', attachment_id: limited.id })).status, 200);
  assert.deepEqual(await ids(await run({ flags: [{ feature: 'openchat_23', stage: 'all' }] }, { operation: 'index' })), [id, limited.id, byTitle.id]);
  // 管理者に出す段階: 管理者だけ見える
  const admins = [{ feature: 'openchat_23', stage: 'admins' }];
  assert.deepEqual(await ids(await run({ flags: admins, role: 'admin' }, { operation: 'index' })), [id, limited.id, byTitle.id]);
  assert.deepEqual(await ids(await run({ flags: admins, role: 'user' }, { operation: 'index' })), [id]);
  // スイッチが読めない・無い時は隠す側
  assert.deepEqual(await ids(await run({ flagsOk: false }, { operation: 'index' })), [id]);
  assert.deepEqual(await ids(await run({ flags: [] }, { operation: 'index' })), [id]);
  // 隠した分があっても、次のページの位置は絞る前の件数で決まる
  const full = Array.from({ length: 500 }, (_, i) => ({ ...limited, id: i.toString(16).padStart(64, '0') }));
  const pageHandler = createHandler(cfg, async url => {
    if (url === cfg.statusUrl) return response({ user_id: '12', status: 'approved', role: 'user', email: 'm@example.com' });
    if (new URL(url).pathname === '/rest/v1/qa_feature_flags') return response(owner);
    return response(full);
  }, () => now);
  const page = await (await pageHandler(request({ source: 'openchat', operation: 'index' }, await issueSession('12', cfg.sessionSecret, now)))).json();
  assert.deepEqual(page, { attachments: [], next_offset: 500 });
});

test('community (non-LINE) attachments do not read the LINE room switch', async () => {
  const handler = createHandler(cfg, async url => {
    if (url === cfg.statusUrl) return response({ user_id: '12', status: 'approved', role: 'user' });
    assert.notEqual(new URL(url).pathname, '/rest/v1/qa_feature_flags');
    assert.doesNotMatch(new URL(url).searchParams.get('select') || '', /route_id/);
    return response([{ id, comment_id: '1' }]);
  }, () => now);
  const res = await handler(request({ operation: 'index' }, await issueSession('12', cfg.sessionSecret, now)));
  assert.equal(res.status, 200);
});
