import test from 'node:test';
import assert from 'node:assert/strict';
import {createProductionAdapter,digest} from '../lib/raimoAuthAdapter.ts';
import {createRaimoAuthGateway} from '../lib/raimoAuthGateway.ts';
function fixture(settings={}){
 const sessions=new Map(),jobs=new Map(),tasks=[],calls=[];let modelResolve;const modelStarted=Promise.withResolvers();
 const c={origin:'https://app.example',raimoBase:'https://app.example/miniAppApi/test',projectUrl:'https://fixture.supabase.co',serviceKey:'service-only',gatewaySecret:'g'.repeat(40),proxySecret:'p'.repeat(40),normalPipelineV2:settings.normalPipelineV2};
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
   if(path==='/internal/normal-answer-v2')return Response.json(settings.envelope||{response:'invalid envelope'});
   if(path==='/chat-sessions/mine/messages-append'){assert.ok(['user','assistant'].includes(body.role));return settings.failHistory?Response.json({errorCode:'unavailable'},{status:503}):Response.json({ok:true});}
   if(path==='/chat-sessions/mine/messages')return new Promise(resolve=>{modelResolve=()=>resolve(Response.json({answer:'normal answer',usedSources:'{}'}));modelStarted.resolve();});
  }
  throw new Error('unexpected test transport');
 };
 const adapter=createProductionAdapter(c,async(a,b)=>a===b,async()=>'',transport,{
  schedule:p=>tasks.push(p),
  semantic:async request=>{const input=await request.json();assert.equal(request.headers.get('x-semantic-shared-secret'),'s'.repeat(43));assert.equal(input.user_id,'one');return Response.json({answer:'semantic answer',usedSources:'{"chunk_keys":["video"]}',relatedChunks:[{chunk_key:'video',start_sec:90,citation_label:'セミナー1'}]});}
 });
 const gateway=createRaimoAuthGateway(adapter.deps);
 const request=(path,body,token='',method='POST')=>gateway(new Request('https://gateway.example'+path,{method,headers:{Origin:c.origin,Authorization:'Bearer '+token},...(body!==undefined?{body:JSON.stringify(body)}:{})}));
 return {request,jobs,sessions,tasks,calls,user,modelReady:modelStarted.promise,finishModel:()=>modelResolve()};
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

const normalEnvelope={response:JSON.stringify({answer:'grounded answer',used_sources:{comment_ids:['42'],chunk_keys:['video']}}),relatedComments:[{comment_id:'42',content:'same evidence'}],relatedLessonComments:[],relatedChunks:[{chunk_key:'video',content:'same video'}]};
test('two-stage normal pipeline saves validated answer and sources once without legacy generation',async()=>{
 const f=fixture({normalPipelineV2:true,envelope:normalEnvelope}),token=await login(f);
 await f.request('/chat-sessions/mine/answer-jobs',input('normal'),token);await Promise.all(f.tasks);
 const job=[...f.jobs.values()][0];assert.equal(job.status,'done');assert.equal(job.result.pipeline,'normal-v2');assert.equal(job.result.answer,'grounded answer');assert.deepEqual(JSON.parse(job.result.usedSources),{comment_ids:['42'],chunk_keys:['video']});
 assert.equal(f.calls.filter(c=>c.url.endsWith('/internal/normal-answer-v2')).length,1);assert.equal(f.calls.filter(c=>c.url.endsWith('/messages')).length,0);
 assert.deepEqual(f.calls.filter(c=>c.url.endsWith('/messages-append')).map(c=>c.body.role),['user','assistant']);
});
test('invalid normal envelope uses legacy once before any history write',async()=>{
 const f=fixture({normalPipelineV2:true}),token=await login(f);
 await f.request('/chat-sessions/mine/answer-jobs',input('normal'),token);await f.modelReady;f.finishModel();await Promise.all(f.tasks);
 assert.equal([...f.jobs.values()][0].result.pipeline,'normal-legacy-fallback');assert.equal([...f.jobs.values()][0].result.answer,'normal answer');assert.equal(f.calls.filter(c=>c.url.endsWith('/messages')).length,1);assert.equal(f.calls.filter(c=>c.url.endsWith('/messages-append')).length,0);
});
test('history failure never triggers a second generation or legacy duplicate messages',async()=>{
 const f=fixture({normalPipelineV2:true,envelope:normalEnvelope,failHistory:true}),token=await login(f);
 await f.request('/chat-sessions/mine/answer-jobs',input('normal'),token);await Promise.all(f.tasks);
 assert.equal([...f.jobs.values()][0].status,'failed');assert.equal(f.calls.filter(c=>c.url.endsWith('/internal/normal-answer-v2')).length,1);assert.equal(f.calls.filter(c=>c.url.endsWith('/messages')).length,0);
});
