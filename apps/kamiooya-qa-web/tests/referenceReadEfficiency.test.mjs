import test from 'node:test';
import assert from 'node:assert/strict';
import {setTimeout as delay} from 'node:timers/promises';
import {createProductionAdapter} from '../lib/raimoAuthAdapter.ts';
const config={origin:'https://app.example',raimoBase:'https://app.example/miniAppApi/test',gatewaySecret:'g'.repeat(40),proxySecret:'p'.repeat(40),projectUrl:'https://fixture.supabase.co',serviceKey:'fixture-service-only'};
test('reference reads overlap with bounded concurrency and preserve every source and original page order',async()=>{
 const keys=Array.from({length:100},(_,i)=>'k'+String(i).padStart(3,'0'));let active=0,max=0,chunkActive=0,maxChunks=0;const paths=[];
 const transport=async(url)=>{
  const u=new URL(url),chunk=u.pathname.endsWith('/knowledge_chunks');active++;max=Math.max(max,active);if(chunk){chunkActive++;maxChunks=Math.max(maxChunks,chunkActive);}paths.push(u);
  try{await delay(15);
   if(u.pathname.endsWith('/app_qa_search_events'))return Response.json([{query_text:'fixture',used_sources:{chunk_keys:keys}}]);
   if(chunk){const part=u.searchParams.get('chunk_key').slice(4,-1).split(',');assert.ok(part.length<=20);return Response.json(part.map(chunk_key=>({chunk_key,content:'evidence'})));}
   if(u.pathname.endsWith('/knowledge_sources'))return Response.json([{id:1,source_key:'s',title:'Original title'}]);
   if(u.pathname.endsWith('/qa_answer_jobs')){assert.equal(u.searchParams.get('user_id'),'eq.one');assert.equal(u.searchParams.get('chat_id'),'eq.mine');return Response.json([{query:'original',result:{answer:'original answer'}}]);}
   throw new Error('unexpected read');
  }finally{active--;if(chunk)chunkActive--;}
 };
 const adapter=createProductionAdapter(config,async()=>false,async()=>'',transport);const result=await adapter.deps.referenceEvents('one','mine');
 assert.deepEqual(result.chunks.map(x=>x.chunk_key),keys);assert.equal(result.jobs[0].result.answer,'original answer');assert.equal(result.sources[0].title,'Original title');assert.ok(max>=3);assert.equal(maxChunks,4);assert.equal(paths.filter(u=>u.pathname.endsWith('/knowledge_chunks')).length,5);
});
