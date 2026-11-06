// Opt-in real-time integration check. No AI calls, production data, or external network.
// QA_WALLCLOCK_TEST=1 node --experimental-strip-types --test tests/qaAnswerWallClock.test.mjs
import test from 'node:test';
import assert from 'node:assert/strict';
import {createServer} from 'node:http';
import {writeFileSync} from 'node:fs';
import {setTimeout as delay} from 'node:timers/promises';
import {createProductionAdapter} from '../lib/raimoAuthAdapter.ts';
import {createRaimoAuthGateway} from '../lib/raimoAuthGateway.ts';

test('normal answers survive real 190s HTTP work and terminate a stalled upstream near the 300s budget',{
 skip:process.env.QA_WALLCLOCK_TEST!=='1',timeout:330000
},async()=>{
 const origin='https://app.example',sessions=new Map(),jobs=new Map(),tasks=[],upstreamCalls=new Map();
 const users=['slow','stalled'].map(id=>({id,email:id+'@example.test',role:'user',status:'approved',password_hash:'fixture-password'}));
 const config={origin,raimoBase:origin+'/miniAppApi/test',projectUrl:'https://fixture.supabase.co',serviceKey:'fixture-service-only',gatewaySecret:'g'.repeat(40),proxySecret:'p'.repeat(40)};
 let gateway,base;
 const server=createServer(async(req,res)=>{
  try{
   const url=new URL(req.url,base);const buffers=[];for await(const part of req)buffers.push(part);const body=Buffer.concat(buffers).toString();
   if(url.pathname==='/upstream'){
    const mode=url.searchParams.get('mode');upstreamCalls.set(mode,(upstreamCalls.get(mode)||0)+1);
    if(mode==='stalled'){req.socket.once('close',()=>{});return;}
    const timer=setTimeout(()=>{res.setHeader('content-type','application/json');res.end(JSON.stringify({answer:'synthetic normal answer',usedSources:'{}'}));},190000);
    res.once('close',()=>clearTimeout(timer));return;
   }
   const request=new Request(base+req.url,{method:req.method,headers:{Origin:origin,Authorization:req.headers.authorization||''},...(body?{body}:{})});
   const response=await gateway(request);
   // The request was processed, but its HTTP response never reached the client.
   if(req.headers['x-drop-response']==='yes'){res.destroy();return;}
   res.writeHead(response.status,Object.fromEntries(response.headers));res.end(await response.text());
  }catch{if(!res.destroyed){res.writeHead(500);res.end('fixture_error');}}
 });
 await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));base='http://127.0.0.1:'+server.address().port;
 const transport=async(url,options={})=>{
  const u=new URL(url),body=options.body?JSON.parse(options.body):{};
  if(u.pathname.endsWith('/rpc/raimo_auth_take_limit'))return Response.json(true);
  if(u.pathname.endsWith('/raimo_auth_sessions')){
   const key=u.searchParams.get('token_hash')?.slice(3);
   if(options.method==='POST'){sessions.set(body.token_hash,body);return new Response(null,{status:201});}
   if(options.method==='DELETE'){sessions.delete(key);return new Response(null,{status:204});}
   return Response.json(sessions.has(key)?[sessions.get(key)]:[]);
  }
  if(u.pathname.endsWith('/rpc/qa_admit_answer_job')){
   const old=[...jobs.values()].find(j=>j.user_id===body.job.user_id&&j.request_id===body.job.request_id);
   if(old)return Response.json(old.request_hash===body.job.request_hash?{job:old,created:false}:{conflict:true});
   if([...jobs.values()].some(j=>j.user_id===body.job.user_id&&j.status==='running'))return Response.json({busy:true});
   const row={...body.job,id:crypto.randomUUID(),status:'running'};jobs.set(row.id,row);return Response.json({job:row,created:true});
  }
  if(u.pathname.endsWith('/qa_answer_jobs')){
   const row=jobs.get(u.searchParams.get('id')?.slice(3));
   if(options.method==='PATCH'){if(row?.status==='running')Object.assign(row,body);return new Response(null,{status:204});}
   return Response.json(row&&row.user_id===u.searchParams.get('user_id')?.slice(3)&&row.chat_id===u.searchParams.get('chat_id')?.slice(3)?[row]:[]);
  }
  if(url.startsWith(config.raimoBase)){
   assert.equal(body.__gateway_secret,config.gatewaySecret);
   const path=u.pathname.slice('/miniAppApi/test'.length);
   if(path.startsWith('/internal/auth-user/'))return Response.json({user:users.find(x=>body.user_id===x.id||body.email===x.email)||null});
   const owner=/^\/internal\/read\/chat-sessions\/(slow|stalled)$/.exec(path);
   if(owner)return Response.json({session:{user_id:owner[1]}});
   const message=/^\/chat-sessions\/(slow|stalled)\/messages$/.exec(path);
   if(message)return fetch(base+'/upstream?mode='+message[1],{...options,headers:{'content-type':'application/json'}});
  }
  throw new Error('unexpected fixture transport');
 };
 const adapter=createProductionAdapter(config,async(a,b)=>a===b,async()=>'',transport,{schedule:p=>tasks.push(p),semantic:async()=>{throw new Error('semantic_not_used');}});
 gateway=createRaimoAuthGateway(adapter.deps);
 const call=(path,token,body,drop=false)=>fetch(base+path,{method:body===undefined?'GET':'POST',headers:{Authorization:'Bearer '+token,...(drop?{'x-drop-response':'yes'}:{})},...(body===undefined?{}:{body:JSON.stringify(body)}),signal:AbortSignal.timeout(10000)});
 const login=async id=>(await(await call('/auth/login','',{email:id+'@example.test',password_hash:'fixture-password'})).json()).auth_token;
 const reports=[];
 try{
  await Promise.all(users.map(async user=>{
   let token=await login(user.id);const started=performance.now();
   const input={request_id:crypto.randomUUID(),mode:'normal',query:'synthetic '+user.id};
   const path='/chat-sessions/'+user.id+'/answer-jobs';
   await assert.rejects(call(path,token,input,true));
   const admitted=await call(path,token,input);assert.equal(admitted.status,202);const job=(await admitted.json()).job_id;
   let reconnected=false,droppedStatus=false,state,maxStatusMs=0,statusReads=0;
   for(;;){
    const elapsed=performance.now()-started;
    if(elapsed>90000&&!reconnected){token=await login(user.id);reconnected=true;}
    if(elapsed>120000&&!droppedStatus){await assert.rejects(call(path+'/'+job,token,undefined,true));droppedStatus=true;}
    const readStart=performance.now(),response=await call(path+'/'+job,token);maxStatusMs=Math.max(maxStatusMs,performance.now()-readStart);statusReads++;
    assert.equal(response.status,200);state=await response.json();
    if(state.status!=='running')break;
    assert.ok(elapsed<310000,'job did not reach terminal state');await delay(5000);
   }
   const elapsed=performance.now()-started;
   if(user.id==='slow'){assert.equal(state.status,'done');assert.equal(state.result.answer,'synthetic normal answer');assert.ok(elapsed>=190000&&elapsed<220000);}
   else {assert.equal(state.status,'failed');assert.equal(state.error,'answer_timeout');assert.ok(elapsed>=280000&&elapsed<310000);}
   const replay=await(await call(path,token,input)).json();assert.equal(replay.job_id,job);assert.equal(replay.status,state.status);
   assert.equal(upstreamCalls.get(user.id),1);assert.equal([...jobs.values()].filter(j=>j.user_id===user.id).length,1);
   const otherToken=await login(user.id==='slow'?'stalled':'slow');assert.equal((await call(path+'/'+job,otherToken)).status,403);
   await call('/auth/logout',token,{});assert.equal((await call(path+'/'+job,token)).status,401);
   const report={case:user.id,elapsed_seconds:Math.round(elapsed)/1000,status:state.status,error:state.error||null,upstream_calls:upstreamCalls.get(user.id),job_count:1,reconnected,dropped_admission:true,dropped_status:droppedStatus,status_reads:statusReads,max_status_ms:Math.round(maxStatusMs)};
   reports.push(report);console.log(JSON.stringify(report));
  }));
  await Promise.all(tasks);
  if(process.env.QA_WALLCLOCK_REPORT)writeFileSync(process.env.QA_WALLCLOCK_REPORT,JSON.stringify({scope:'local production gateway/adapters plus real delayed HTTP; not hosted Supabase execution',ai_calls:0,reports},null,2),{mode:0o600});
 }finally{server.closeAllConnections();await new Promise(resolve=>server.close(resolve));}
});
