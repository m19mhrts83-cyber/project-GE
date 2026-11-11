import test from 'node:test';
import assert from 'node:assert/strict';
import {createProductionAdapter,digest} from '../lib/raimoAuthAdapter.ts';
import {createRaimoAuthGateway} from '../lib/raimoAuthGateway.ts';
function fixture(opts={}){
 const sessions=new Map(),jobs=new Map(),tasks=[],calls=[],semanticInputs=[];let modelResolve;
 const c={origin:'https://app.example',raimoBase:'https://app.example/miniAppApi/test',projectUrl:'https://fixture.supabase.co',serviceKey:'service-only',gatewaySecret:'g'.repeat(40),proxySecret:'p'.repeat(40)};
 const user={id:'one',email:'owner@example.test',role:'user',status:'approved',password_hash:'fixture-password'};
 const transport=async(url,options={})=>{
  const u=new URL(url),body=options.body?JSON.parse(options.body):{};calls.push({url,body});
  if(u.pathname.endsWith('/rpc/raimo_auth_take_limit'))return Response.json(true);
  if(u.pathname.endsWith('/raimo_auth_sessions')){
   const key=u.searchParams.get('token_hash')?.slice(3);
   if(options.method==='POST'){sessions.set(body.token_hash,body);return new Response(null,{status:201});}
   if(options.method==='DELETE'){sessions.delete(key);return new Response(null,{status:204});}
   return Response.json(sessions.has(key)?[sessions.get(key)]:[]);
  }
  if(u.pathname.endsWith('/rpc/qa_admit_answer_job')){
   const old=[...jobs.values()].find(j=>j.request_id===body.job.request_id&&j.user_id===body.job.user_id);
   if(old)return Response.json({job:old,created:false});
   const job={...body.job,id:crypto.randomUUID(),status:'running'};jobs.set(job.id,job);return Response.json({job,created:true});
  }
  if(opts.flags&&u.pathname.endsWith('/qa_feature_flags'))return Response.json(opts.flags);
  if(opts.cache&&u.pathname.endsWith('/qa_answer_cache')){opts.cache.push({method:options.method||'GET',body});return Response.json([]);}
  if(u.pathname.endsWith('/qa_answer_jobs')&&u.searchParams.get('id')?.startsWith('neq.')){
   assert.equal(u.searchParams.get('status'),'eq.done');assert.equal(u.searchParams.get('user_id'),'eq.one');assert.equal(u.searchParams.get('chat_id'),'eq.mine');
   return Response.json(opts.prior||[]);
  }
  if(u.pathname.endsWith('/qa_answer_jobs')){
   const id=u.searchParams.get('id')?.slice(3),job=jobs.get(id);
   if(options.method==='PATCH'){if(job.status==='running')Object.assign(job,body);return new Response(null,{status:204});}
   return Response.json(job&&job.user_id===u.searchParams.get('user_id')?.slice(3)&&job.chat_id===u.searchParams.get('chat_id')?.slice(3)?[job]:[]);
  }
  if(url.startsWith(c.raimoBase)){
   assert.equal(body.__gateway_secret,c.gatewaySecret);
   const path=u.pathname.slice('/miniAppApi/test'.length);
   if(path.startsWith('/internal/auth-user/'))return Response.json({user});
   if(path==='/internal/read/chat-sessions/mine')return Response.json({session:{user_id:'one'}});
   if(path==='/internal/read/chat-sessions/theirs')return Response.json({session:{user_id:'two'}});
   if(path==='/semantic-search-config')return Response.json({url:c.projectUrl+'/functions/v1/semantic-search',secret:'s'.repeat(43)});
   if(path==='/chat-sessions/mine/messages-append'){assert.ok(['user','assistant'].includes(body.role));return Response.json({ok:true});}
   if(path==='/chat-sessions/mine/messages')return new Promise(resolve=>{modelResolve=()=>resolve(Response.json({answer:'normal answer',usedSources:'{}'}));});
  }
  throw new Error('unexpected test transport');
 };
 const adapter=createProductionAdapter(c,async(a,b)=>a===b,async()=>'',transport,{
  schedule:p=>tasks.push(p),
  semantic:async request=>{const input=await request.json();semanticInputs.push(input);assert.equal(request.headers.get('x-semantic-shared-secret'),'s'.repeat(43));assert.equal(input.user_id,'one');return Response.json({answer:'semantic answer',usedSources:'{"chunk_keys":["video"]}',relatedChunks:[{chunk_key:'video',start_sec:90,citation_label:'セミナー1'}]});}
 });
 const gateway=createRaimoAuthGateway(adapter.deps);
 const request=(path,body,token='',method='POST')=>gateway(new Request('https://gateway.example'+path,{method,headers:{Origin:c.origin,Authorization:'Bearer '+token},...(body!==undefined?{body:JSON.stringify(body)}:{})}));
 return {request,jobs,sessions,tasks,calls,user,semanticInputs,finishModel:()=>modelResolve()};
}
const input=mode=>({request_id:'11111111-1111-4111-8111-111111111111',mode,query:'question',user_id:'two',auth_version:'forged'});
async function login(f){const r=await f.request('/auth/login',{email:'owner@example.test',password_hash:'fixture-password'});return (await r.json()).auth_token;}
const flush=async()=>{for(let i=0;i<30;i++)await Promise.resolve();};
test('actual gateway and production adapters admit normal jobs before generation, then return results',async()=>{
 const f=fixture(),token=await login(f);
 const r=await f.request('/chat-sessions/mine/answer-jobs',input('normal'),token);assert.equal(r.status,202);const accepted=await r.json();
 await flush();assert.equal(accepted.status,'running');assert.equal(f.jobs.size,1);assert.equal([...f.jobs.values()][0].user_id,'one');assert.notEqual([...f.jobs.values()][0].auth_version,'forged');
 const replay=await f.request('/chat-sessions/mine/answer-jobs',input('normal'),token);assert.equal((await replay.json()).job_id,accepted.job_id);
 f.finishModel();await Promise.all(f.tasks);
 const done=await f.request('/chat-sessions/mine/answer-jobs/'+accepted.job_id,undefined,token,'GET');assert.equal(done.status,200);assert.equal((await done.json()).result.answer,'normal answer');
 assert.equal(f.calls.filter(c=>c.url.endsWith('/chat-sessions/mine/messages')).length,1);
});
test('semantic jobs run the shared handler in background and save one user/assistant pair',async()=>{
 const f=fixture(),token=await login(f);const r=await f.request('/chat-sessions/mine/answer-jobs',input('semantic'),token);const accepted=await r.json();await Promise.all(f.tasks);
 assert.equal(f.calls.filter(c=>c.url.endsWith('/internal/auth-user/user_id')).length,2); // gateway + worker each check once, without caching membership
 const done=await f.request('/chat-sessions/mine/answer-jobs/'+accepted.job_id,undefined,token,'GET');const result=(await done.json()).result;
 assert.equal(result.answer,'semantic answer');assert.equal(result.relatedChunks[0].citation_label,'セミナー1');
 const messages=f.calls.filter(c=>c.url.endsWith('/messages-append'));assert.deepEqual(messages.map(x=>x.body.role),['user','assistant']);
 await f.request('/auth/logout',{},token);assert.equal((await f.request('/chat-sessions/mine/answer-jobs/'+accepted.job_id,undefined,token,'GET')).status,401);
});
test('gateway denies unauthenticated and cross-owner jobs before admission',async()=>{
 const f=fixture();assert.equal((await f.request('/chat-sessions/mine/answer-jobs',input('normal'))).status,401);
 const token=await login(f);assert.equal((await f.request('/chat-sessions/theirs/answer-jobs',input('normal'),token)).status,403);assert.equal(f.jobs.size,0);
});

// スイッチ chat_context（2026-11-11）: 同じチャットの直前のやり取りを、意味検索・より詳しく調べるに渡す。
const prior=[{query:'2問目: 修繕費の相場は？',result:{answer:'外壁は…'},created_at:'2026-11-11T01:01:00Z'},{query:'1問目: 外壁塗装の時期は？',result:{answer:'10〜15年…'},created_at:'2026-11-11T01:00:00Z'}];
const owner=[{feature:'chat_context',stage:'owner',owner_ids:['owner@example.test']},{feature:'cost_saving',stage:'owner',owner_ids:['owner@example.test']}];
test('chat_context: the owner sends the previous turns (oldest first) and skips answer reuse',async()=>{
 const cache=[];const f=fixture({flags:owner,prior,cache}),token=await login(f);
 await f.request('/chat-sessions/mine/answer-jobs',input('semantic'),token);await Promise.all(f.tasks);
 assert.deepEqual(f.semanticInputs[0].history,[{question:'1問目: 外壁塗装の時期は？',answer:'10〜15年…'},{question:'2問目: 修繕費の相場は？',answer:'外壁は…'}]);
 assert.equal(cache.length,0); // 文脈つきの答えは使い回さない・保存しない
 assert.equal(f.semanticInputs[0].clarify,true); // 調べる前の言い直し・聞き返しを頼む
});
test('chat_context: deep mode also carries the previous turns',async()=>{
 const f=fixture({flags:owner,prior}),token=await login(f);
 await f.request('/chat-sessions/mine/answer-jobs',input('deep'),token);await Promise.all(f.tasks);
 assert.equal(f.semanticInputs[0].history.length,2);
});
test('chat_context: off or not named means no history (unchanged behaviour)',async()=>{
 for(const flags of [[{feature:'chat_context',stage:'off',owner_ids:['owner@example.test']}],[{feature:'chat_context',stage:'owner',owner_ids:['someone@else.test']}]]){
  const f=fixture({flags,prior}),token=await login(f);
  await f.request('/chat-sessions/mine/answer-jobs',input('deep'),token);await Promise.all(f.tasks);
  assert.equal(f.semanticInputs[0].history,undefined);
  assert.equal(f.semanticInputs[0].clarify,undefined);
 }
});
