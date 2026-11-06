import test from 'node:test';
import assert from 'node:assert/strict';
import {createAnswerJobs,compactAnswerResult} from '../lib/qaAnswerJobs.ts';
const actor={id:'one',authVersion:'v'.repeat(64),sessionRef:'s'.repeat(64)};
const request=(mode='normal',id='11111111-1111-4111-8111-111111111111')=>({query:'question',mode,request_id:id});
function fixture(){
 let time=1800000000000,executeCount=0,authorized=true,resolveExecution,rejectExecution;
 const rows=new Map(),tasks=[];
 const copy=x=>structuredClone(x);
 const store={
  async admit(input){
   const old=[...rows.values()].find(j=>j.user_id===input.user_id&&j.request_id===input.request_id);
   if(old)return old.request_hash===input.request_hash?{job:copy(old),created:false}:{conflict:true};
   const active=[...rows.values()].find(j=>j.user_id===input.user_id&&j.status==='running'&&Date.parse(j.deadline_at)>time);
   if(active)return active.request_hash===input.request_hash&&active.chat_id===input.chat_id?{job:copy(active),created:false}:{busy:true};
   const job={...input,id:crypto.randomUUID(),status:'running'};rows.set(job.id,job);return {job:copy(job),created:true};
  },
  async get(id,uid,chat){const j=rows.get(id);return j&&j.user_id===uid&&j.chat_id===chat?copy(j):null;},
  async finish(id,result,error){const j=rows.get(id);if(j.status==='running'){j.status=error?'failed':'done';j.result=result;j.error_code=error;}}
 };
 const service=createAnswerJobs({store,now:()=>time,schedule:p=>tasks.push(p),authorize:async()=>authorized,
  timeout:()=>new AbortController().signal,
  execute:async()=>{executeCount++;return new Promise((resolve,reject)=>{resolveExecution=resolve;rejectExecution=reject;});}
 });
 return {service,rows,tasks,count:()=>executeCount,advance:ms=>{time+=ms;},resolve:r=>resolveExecution(r),reject:e=>rejectExecution(e),deny:()=>{authorized=false;}};
}
for(const mode of ['normal','semantic'])for(const duration of [90000,140000,240000]){
 test(`${mode}: ${duration/1000}s work is admitted immediately and returned by short status calls`,async()=>{
  const f=fixture();const admitted=await f.service.start(actor,'mine',request(mode));
  assert.equal(admitted.status,'running');assert.equal(f.count(),1);
  f.advance(duration);f.resolve({answer:'completed',usedSources:'{}'});await Promise.all(f.tasks);
  const done=await f.service.get(actor,'mine',admitted.job_id);assert.equal(done.status,'done');assert.equal(done.result.answer,'completed');assert.equal(f.count(),1);
 });
}
test('lost admission response, duplicate submissions and status reads never generate twice',async()=>{
 const f=fixture();const first=await f.service.start(actor,'mine',request());
 const replay=await f.service.start(actor,'mine',request());
 const activeReuse=await f.service.start(actor,'mine',request('normal','22222222-2222-4222-8222-222222222222'));
 assert.equal(replay.job_id,first.job_id);assert.equal(activeReuse.job_id,first.job_id);assert.equal(f.count(),1);
 await assert.rejects(f.service.start(actor,'mine',{...request(),query:'different'}),e=>e.code==='answer_request_conflict');
 await assert.rejects(f.service.start(actor,'other',request('semantic','33333333-3333-4333-8333-333333333333')),e=>e.code==='answer_in_progress');
 f.resolve({answer:'one'});await Promise.all(f.tasks);
 assert.equal((await f.service.start(actor,'mine',request())).status,'done');assert.equal(f.count(),1);
});
test('cross-user, cross-chat and changed credential versions cannot retrieve results',async()=>{
 const f=fixture();const r=await f.service.start(actor,'mine',request());f.resolve({answer:'private'});await Promise.all(f.tasks);
 for(const [who,chat] of [[{...actor,id:'other'},'mine'],[actor,'other'],[{...actor,authVersion:'changed'},'mine']])await assert.rejects(f.service.get(who,chat,r.job_id),e=>e.code==='answer_not_found');
});
test('a lost worker or exceeded processing budget becomes terminal without automatic resubmission',async()=>{
 const f=fixture();const r=await f.service.start(actor,'mine',request());f.advance(300001);
 assert.equal((await f.service.get(actor,'mine',r.job_id)).error,'answer_timeout');
 f.resolve({answer:'late'});await Promise.all(f.tasks);assert.equal((await f.service.get(actor,'mine',r.job_id)).status,'failed');
 assert.equal((await f.service.start(actor,'mine',request())).status,'failed');assert.equal(f.count(),1);
});
test('revoked admission authorization and upstream exceptions do not leak private details',async()=>{
 const denied=fixture();denied.deny();const a=await denied.service.start(actor,'mine',request());await Promise.all(denied.tasks);
 assert.equal(denied.count(),0);assert.equal((await denied.service.get(actor,'mine',a.job_id)).error,'authorization_changed');
 const f=fixture();const b=await f.service.start(actor,'mine',request());f.reject(new Error('private service credential'));await Promise.all(f.tasks);
 const state=await f.service.get(actor,'mine',b.job_id);assert.equal(state.error,'answer_failed');assert.equal(JSON.stringify(state).includes('credential'),false);
});
test('stored answer payloads omit emails, IPs and unrelated server fields',()=>{
 const r=compactAnswerResult({answer:'ok',secret:'hidden',relatedComments:[{comment_id:'1',posted_at:'2026-11-01',content:'x'.repeat(2000),author_email:'private',ip_address:'private',password_hash:'private'}],usedSources:{comment_ids:['1']}});
 assert.equal(r.relatedComments[0].content.length,800);assert.equal(JSON.stringify(r).includes('private'),false);assert.equal('secret' in r,false);assert.equal(JSON.parse(r.usedSources).comment_ids[0],'1');
});
