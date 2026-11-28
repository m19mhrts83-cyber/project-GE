import test from 'node:test';
import assert from 'node:assert/strict';
import {createProductionAdapter,digest} from '../lib/raimoAuthAdapter.ts';
import {createRaimoAuthGateway} from '../lib/raimoAuthGateway.ts';
const origin='https://app.example';
function fixture(){
 const store=new Map(), calls=[];let limit=true;
 const users=[{id:'1',email:'user@example.test',role:'user',status:'approved',password_hash:'fixture-password',reset_token:'private-reset'},{id:'2',email:'admin@example.test',role:'master_admin',status:'approved',password_hash:'fixture-password'}];
 const config={origin,raimoBase:origin+'/miniAppApi/test',gatewaySecret:'g'.repeat(40),proxySecret:'p'.repeat(40),projectUrl:'https://fixture.supabase.co',serviceKey:'service-only'};
 const transport=async(url,opts={})=>{
  const u=new URL(url),body=opts.body?JSON.parse(opts.body):{};calls.push({url,opts,body});
  if(u.pathname.endsWith('/rpc/raimo_auth_take_limit'))return Response.json(limit);
  if(u.pathname.endsWith('/raimo_auth_sessions')){
   if(opts.method==='POST'){assert.match(body.token_hash,/^[0-9a-f]{64}$/);store.set(body.token_hash,body);return new Response(null,{status:201});}
   const key=u.searchParams.get('token_hash')?.slice(3);
   if(opts.method==='DELETE'){store.delete(key);return new Response(null,{status:204});}
   return Response.json(store.has(key)?[store.get(key)]:[]);
  }
  if(url.startsWith(config.raimoBase)){
   assert.equal(opts.method==='GET',false);assert.equal(u.search,'');assert.equal(body.__gateway_secret,config.gatewaySecret);
   const path=u.pathname.slice('/miniAppApi/test'.length);
   if(path.startsWith('/internal/auth-user/')){const field=path.split('/').at(-1);return Response.json({user:users.find(x=>String(x[field==='user_id'?'id':field])===String(body[field]))||null});}
   if(path==='/internal/read/chat-sessions/mine')return Response.json({session:{user_id:'1'}});
   if(path==='/internal/read/chat-sessions/theirs')return Response.json({session:{user_id:'2'}});
   if(path==='/chat-sessions/mine/messages-append'){
    if(!['user','assistant'].includes(body.role))return Response.json({errorCode:'message_role_required'},{status:400});
    return Response.json({ok:true});
   }
   if(path==='/internal/read/admin/users')return Response.json({users});
   if(path==='/internal/read/comments')return Response.json({comments:[]});
   if(path.startsWith('/auth/'))return Response.json({success:true,id:'3'});
   if(path.startsWith('/notify/'))return Response.json({ok:true});
   return Response.json({ok:true});
  }
  if(u.pathname.endsWith('/community-attachments'))return Response.json({token:'fixture-attachment'});
  throw new Error('unexpected_transport');
 };
 const adapter=createProductionAdapter(config,async(a,b)=>a===b,async p=>'hashed:'+p,transport);
 const gateway=createRaimoAuthGateway(adapter.deps);
 const request=(path,body,token='',method='POST')=>gateway(new Request('https://gateway.example'+path,{method,headers:{Origin:origin,Authorization:'Bearer '+token},...(body?{body:JSON.stringify(body)}:{})}));
 const login=async(email='user@example.test')=>{const r=await request('/auth/login',{email,password_hash:'fixture-password'});assert.equal(r.status,200);return (await r.json()).auth_token;};
 return {adapter,request,login,users,store,calls,config,disableLimit:()=>limit=false};
}
test('real adapters persist only token hashes and survive a new gateway instance',async()=>{
 const f=fixture(),token=await f.login();assert.equal(f.store.has(token),false);assert.equal(f.store.has(await digest(token)),true);
 assert.equal(JSON.stringify([...f.store.values()]).includes('fixture-password'),false);
 assert.equal((await f.request('/comments',null,token,'GET')).status,200);
 const next=createRaimoAuthGateway(f.adapter.deps);const r=await next(new Request('https://gateway.example/comments',{headers:{Origin:origin,Authorization:'Bearer '+token}}));assert.equal(r.status,200);
 assert.equal((await f.request('/chat-sessions/theirs/messages',{message:'x'},token)).status,403);
 assert.equal((await f.request('/chat-sessions/mine/messages',{user_id:'2',message:'x'},token)).status,200);
 const status=await f.adapter.status('1',await digest(token));assert.equal(status.session_active,true);assert.equal(status.email,'user@example.test');
 assert.equal((await f.adapter.status('2',await digest(token))).session_active,false);
 await f.request('/auth/logout',{},token);assert.equal((await f.adapter.status('1',await digest(token))).session_active,false);
});
test('production membership version revokes and admin lists never return password or reset data',async()=>{
 const f=fixture(),token=await f.login();f.users[0].password_hash='changed';assert.equal((await f.request('/comments',null,token,'GET')).status,403);
 const admin=await f.login('admin@example.test');const r=await f.request('/admin/users',null,admin,'GET');assert.equal(r.status,200);const text=await r.text();assert.equal(/password_hash|fixture-password|reset_token|private-reset/.test(text),false);
 assert.equal((await f.request('/admin/users/1/set-role',{role:'master_admin'},admin)).status,400);
});
test('registrations hash credentials, reset URLs are generated on server, throttle is shared',async()=>{
 const f=fixture();const r=await f.request('/auth/register',{email:'new@example.test',password_hash:'new-password',role:'master_admin',status:'approved'});assert.equal(r.status,200);
 const registration=f.calls.find(c=>c.url.endsWith('/auth/register'));assert.equal(registration.body.password_hash,'hashed:new-password');assert.equal('role' in registration.body,false);
 await f.request('/auth/forgot-password/issue',{email:'user@example.test',token:'attacker-choice',expires_at:'2999-01-01'});
 const issue=f.calls.find(c=>c.url.endsWith('/auth/forgot-password/issue'));assert.match(issue.body.token,/^[0-9a-f]{64}$/);assert.notEqual(issue.body.token,'attacker-choice');
 const mail=f.calls.find(c=>c.url.endsWith('/notify/password-reset'));assert.ok(mail.body.reset_url.startsWith(origin+'/#reset-password?token='));assert.equal(mail.body.reset_url.includes('attacker-choice'),false);assert.match(mail.body.expires_at,/^\d{4}年\d{1,2}月\d{1,2}日 \d{2}:\d{2}$/);
 f.disableLimit();assert.equal((await f.request('/auth/login',{email:'new@example.test',password_hash:'new-password'})).status,429);
});
test('expired password reset and wrong tokens cannot change credentials',async()=>{
 const f=fixture();const token='t'.repeat(64);f.users[0].reset_token=await digest(token);f.users[0].reset_expires_at='2000-01-01';
 assert.equal((await f.request('/auth/reset-password',{token,password_hash:'new-password'})).status,400);
 f.users[0].reset_expires_at=new Date(Date.now()+60000).toISOString();assert.equal((await f.request('/auth/reset-password',{token,password_hash:'new-password'})).status,200);
 const call=f.calls.find(c=>c.url.endsWith('/auth/reset-password'));assert.equal(call.body.password_hash,'hashed:new-password');assert.equal(call.body.token,await digest(token));
});
test('staff cannot read a master transfer token or write reserved transfer records',async()=>{
 const f=fixture();f.users[0].role='admin';const token=await f.login();
 assert.equal((await f.request('/admin/master-transfer/pending',null,token,'GET')).status,403);
 assert.equal((await f.request('/admin/comments',{comment_id:'admin_master_xfer_pending',source_type:'__master_xfer__',content:'forged'},token)).status,403);
 const master=await f.login('admin@example.test');
 assert.equal((await f.request('/admin/role-requests/1/approve',{new_role:'master_admin'},master,'PUT')).status,400);
});
test('proof is never accepted for an internal browser route and failures hide upstream secrets',async()=>{
 const f=fixture(),token=await f.login();
 assert.equal((await f.request('/internal/auth-user/email',{email:'admin@example.test',__gateway_secret:f.config.gatewaySecret},token)).status,403);
 const failing=createProductionAdapter(f.config,async()=>true,async()=>'',async()=>{throw new Error('private-source-body');});
 const gateway=createRaimoAuthGateway(failing.deps);const r=await gateway(new Request('https://gateway.example/auth/login',{method:'POST',body:JSON.stringify({email:'a@example.test',password_hash:'x'})}));
 assert.equal(r.status,503);assert.equal((await r.text()).includes('private-source-body'),false);
});

test('semantic message appends preserve message roles without accepting membership roles',async()=>{
 const f=fixture(),token=await f.login();
 for(const role of ['user','assistant']){
  const r=await f.request('/chat-sessions/mine/messages-append',{role,content:'semantic message',user_id:'2',actor_user_id:'2'},token);
  assert.equal(r.status,200);
  const sent=f.calls.filter(c=>c.url.endsWith('/chat-sessions/mine/messages-append')).at(-1).body;
  assert.equal(sent.role,role);assert.equal(sent.actor_user_id,'1');assert.equal('user_id' in sent,false);
 }
 for(const role of ['admin','master_admin','system',null,['user']]){
  assert.equal((await f.request('/chat-sessions/mine/messages-append',{role,content:'x'},token)).status,400);
 }
 assert.equal((await f.request('/chat-sessions/theirs/messages-append',{role:'assistant',content:'x'},token)).status,403);
 await f.request('/chat-sessions',{role:'master_admin',user_id:'2',initial_message:'x'},token);
 const sent=f.calls.filter(c=>c.url.endsWith('/chat-sessions')).at(-1).body;
 assert.equal('role' in sent,false);assert.equal(sent.user_id,'1');
});

test('the semantic configuration route is gone: no member session receives a search credential',async()=>{
 const f=fixture(),token=await f.login();
 const r=await f.request('/semantic-search-config',{},token);
 assert.equal(r.status,403);assert.equal(/secret/i.test(await r.text()),false);
 assert.equal(f.calls.some(c=>c.url.endsWith('/semantic-search-config')),false);
 assert.equal('semanticConfig' in f.adapter.deps,false);
});
test('server windows are called only with the gateway proof, at fixed destinations, and never with a member-side key',async()=>{
 const f=fixture(),sent=[];
 const adapter=createProductionAdapter(f.config,async()=>true,async()=>'',async(url,opts={})=>{sent.push({url,opts});return Response.json({ok:true,secret:'never-forwarded'});});
 const r=await adapter.deps.serverFunction('qa-analytics',{days:7});
 assert.equal(r.status,200);assert.equal(sent[0].url,f.config.projectUrl+'/functions/v1/qa-analytics');
 assert.equal(sent[0].opts.headers['X-Gateway-Proof'],f.config.gatewaySecret);assert.equal('X-Semantic-Shared-Secret' in sent[0].opts.headers,false);
 await assert.rejects(()=>adapter.deps.serverFunction('raimo-auth',{}));
 await adapter.deps.openchatSearch('1',{query:'q',user_id:'2',list_openchat:false});
 const body=JSON.parse(sent[1].opts.body);
 assert.equal(sent[1].url,f.config.projectUrl+'/functions/v1/semantic-search');assert.equal(body.user_id,'1');assert.equal(body.list_openchat,true);assert.equal(body.session_id,null);
});

test('パスワード再設定メールの有効期限は日本時間の「年月日 時:分」', async () => {
  const { jstDeadlineLabel } = await import('../lib/raimoAuthAdapter.ts');
  assert.equal(jstDeadlineLabel('2026-11-15T03:59:40.475Z'), '2026年11月15日 12:59');
  assert.equal(jstDeadlineLabel('2026-12-31T15:05:00Z'), '2027年1月1日 00:05');
  assert.equal(jstDeadlineLabel('壊れた値'), '');
});

test('Raimo が errorCode なし（status と message だけ）で返しても、名簿外は not_on_roster として画面に渡す（2026-11-20）',async()=>{
 const config={origin,raimoBase:origin+'/miniAppApi/test',gatewaySecret:'g'.repeat(40),proxySecret:'p'.repeat(40),projectUrl:'https://fixture.supabase.co',serviceKey:'service-only'};
 const transport=async(url,opts={})=>{
  const u=new URL(url);
  if(u.pathname.endsWith('/rpc/raimo_auth_take_limit'))return Response.json(true);
  if(url.startsWith(config.raimoBase)&&u.pathname.endsWith('/auth/register-roster'))return Response.json({status:400,message:'名簿に一致する会員が見つかりません'},{status:400});
  if(url.startsWith(config.raimoBase)&&u.pathname.endsWith('/auth/register'))return Response.json({status:400,message:'このメールアドレスは既に登録されています。退会済みの場合は同じ内容でもう一度「アカウント作成」してください（再登録）。それ以外はログインまたはパスワード再設定をご利用ください'},{status:400});
  return Response.json({},{status:500});
 };
 const adapter=createProductionAdapter(config,async()=>true,async p=>'hashed:'+p,transport);
 const gw=createRaimoAuthGateway(adapter.deps);
 const body={email:'new@example.test',password_hash:'longenough1',member_no:'X1',name:'名前',prefecture:'愛知県'};
 const r1=await gw(new Request(origin+'/auth/register-roster',{method:'POST',headers:{origin,'content-type':'application/json'},body:JSON.stringify(body)}));
 assert.equal(r1.status,400);assert.equal((await r1.json()).errorCode,'not_on_roster');
 const r2=await gw(new Request(origin+'/auth/register',{method:'POST',headers:{origin,'content-type':'application/json'},body:JSON.stringify(body)}));
 assert.equal((await r2.json()).errorCode,'email_taken');
});
