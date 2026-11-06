import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
function load(){
 const values=new Map();const storage={getItem:k=>values.get(k)||null,setItem:(k,v)=>values.set(k,v),removeItem:k=>values.delete(k)};
 const app=vm.runInNewContext(readFileSync(new URL('../public/raimo/app.js',import.meta.url),'utf8')+'\nApp;',{
  document:{addEventListener(){},getElementById:()=>null},window:{setTimeout,clearTimeout},console,URL,fetch,Intl,Date,crypto,AbortSignal,AbortController,sessionStorage:storage
 });
 app.authGatewayBase='https://gateway.example';app.state.currentUser={id:'one'};app.retryDelay=async()=>{};app.answerPollDelay=async()=>{};return {app,storage};
}
const job='11111111-1111-4111-8111-111111111111';
test('frontend resumes polling after disconnection without sending another generation request',async()=>{
 const {app}=load();let submitted=0,statusCalls=0;
 app.apiClient=async(method)=>{
  if(method==='POST'){submitted++;return {job_id:job,status:'running'};}
  if(statusCalls++<3){const e=new Error('temporary');e.httpStatus=503;throw e;}
  return {job_id:job,status:'done',result:{answer:'completed'}};
 };
 await assert.rejects(app.runAnswerJob('mine','question','semantic',new AbortController().signal));
 assert.equal(submitted,1);assert.equal(app.state.pendingAnswerRequest.jobId,job);
 const result=await app.runAnswerJob('mine','question','semantic',new AbortController().signal);
 assert.equal(result.answer,'completed');assert.equal(submitted,1);app.clearPendingAnswer();assert.equal(app.readPendingAnswer(),null);
});
test('pending request identifiers survive admission response loss and are reused',async()=>{
 const {app}=load();const ids=[];let attempts=0;
 app.apiClient=async(method,path,body)=>{
  if(method==='POST'){ids.push(body.request_id);if(attempts++<3){const e=new Error('lost response');e.httpStatus=503;throw e;}return {job_id:job,status:'running'};}
  return {job_id:job,status:'done',result:{answer:'one answer'}};
 };
 await assert.rejects(app.runAnswerJob('mine','question','normal',new AbortController().signal));
 app.state.pendingAnswerRequest=null;assert.ok(app.readPendingAnswer());
 assert.equal((await app.runAnswerJob('mine','question','normal',new AbortController().signal)).answer,'one answer');
 assert.equal(new Set(ids).size,1);
});
test('a late result cannot cross a logout or user switch',async()=>{
 const {app}=load();let resolveStatus;
 app.apiClient=async method=>method==='POST'?{job_id:job,status:'running'}:new Promise(r=>{resolveStatus=r;});
 const pending=app.runAnswerJob('mine','private question','normal',new AbortController().signal);
 for(let i=0;i<20&&!resolveStatus;i++)await Promise.resolve();
 app.state.currentUser={id:'two'};resolveStatus({job_id:job,status:'done',result:{answer:'private'}});
 await assert.rejects(pending,e=>e.name==='AbortError');
 app.state.pendingAnswerRequest=null;assert.equal(app.readPendingAnswer(),null);
});
test('terminal failures clear the pending request and do not automatically regenerate',async()=>{
 const {app}=load();let posts=0;
 app.apiClient=async method=>{if(method==='POST'){posts++;return {job_id:job,status:'running'};}return {job_id:job,status:'failed',error:'answer_timeout'};};
 await assert.rejects(app.runAnswerJob('mine','question','normal',new AbortController().signal),/制限時間/);
 assert.equal(posts,1);assert.equal(app.state.pendingAnswerRequest,null);
});
