import assert from 'node:assert/strict';
import {handleSemanticSearch} from './handler.ts';

Deno.test('cached query vectors still retrieve fresh sources and generate each answer with unchanged evidence',async()=>{
 const keys=['GEMINI_API_KEY','SUPABASE_URL','SUPABASE_SERVICE_ROLE_KEY','SEMANTIC_SEARCH_SHARED_SECRET','SEMANTIC_SEARCH_DISABLED'];
 const saved=keys.map(k=>Deno.env.get(k)),originalFetch=globalThis.fetch;
 const fixtures=['fixture-provider','https://fixture.supabase.co','fixture-service','fixture-semantic','0'];
 keys.forEach((k,i)=>Deno.env.set(k,fixtures[i]));
 let revision=1,embeddingCalls=0,generationCalls=0;const queries:any[]=[],events:any[]=[],prompts:string[]=[];
 globalThis.fetch=async(input,init)=>{
  const url=new URL(input instanceof Request?input.url:String(input));
  const body=typeof init?.body==='string'?JSON.parse(init.body):{};
  if(url.pathname.endsWith(':embedContent')){embeddingCalls++;return Response.json({embedding:{values:Array.from({length:768},(_,i)=>(i+1)/1000)}});}
  if(url.pathname.endsWith(':generateContent')){generationCalls++;const prompt=body.contents[0].parts[0].text;prompts.push(prompt);assert.ok(prompt.includes('fresh-comment-'+revision));assert.ok(prompt.includes('fresh-video-'+revision));assert.ok(prompt.includes('fresh-line-'+revision));return Response.json({candidates:[{content:{parts:[{text:'fresh-answer-'+revision+' (コミュニティ1、セミナー1、LINEオプチャ1)'}]}}],usageMetadata:{promptTokenCount:100,candidatesTokenCount:20}});}
  if(url.pathname.includes('/rpc/')){
   queries.push({path:url.pathname,body});
   if(url.pathname.endsWith('/match_comments_semantic'))return Response.json([{comment_id:'42',posted_at:'2026-11-01',author_name:'fixture',content:'fresh-comment-'+revision,similarity:0.9}]);
   if(url.pathname.endsWith('/match_chunks_semantic'))return Response.json([{chunk_key:'k',source_id:1,start_sec:61,content:'fresh-video-'+revision,similarity:0.9}]);
   if(url.pathname.endsWith('/match_openchat_semantic'))return Response.json([{id:'line',posted_at:'2026-11-01',content:'fresh-line-'+revision,similarity:0.9}]);
   if(url.pathname.endsWith('/search_openchat_keyword'))return Response.json([]);
  }
  if(url.pathname.endsWith('/knowledge_sources'))return Response.json([{id:1,source_key:'s',title:'fixture video',video_url:'https://vimeo.com/123'}]);
  if(url.pathname.endsWith('/app_qa_search_events')){events.push(body);return Response.json([], {status:201});}
  throw new Error('unexpected fixture transport');
 };
 try{
  const query='quality-fixture-'+crypto.randomUUID();
  const request=()=>new Request('https://fixture.supabase.co/functions/v1/semantic-search',{method:'POST',headers:{'x-semantic-shared-secret':'fixture-semantic'},body:JSON.stringify({query})});
  const firstResponse=await handleSemanticSearch(request());assert.equal(firstResponse.status,200);const first=await firstResponse.json();
  revision=2;const secondResponse=await handleSemanticSearch(request());assert.equal(secondResponse.status,200);const second=await secondResponse.json();
  assert.equal(embeddingCalls,1);assert.equal(generationCalls,2);assert.equal(first.meta.embeddingCacheHit,false);assert.equal(second.meta.embeddingCacheHit,true);
  assert.equal(second.answer,'fresh-answer-2 (コミュニティ1、セミナー1、LINEオプチャ1)');assert.equal(second.relatedComments[0].content,'fresh-comment-2');
  assert.deepEqual(first.referenceLabels,second.referenceLabels);assert.deepEqual(first.usedSources,second.usedSources);assert.equal(prompts.length,2);
  assert.equal(queries.length,8);assert.deepEqual(queries.slice(0,4).sort((a,b)=>a.path.localeCompare(b.path)),queries.slice(4).sort((a,b)=>a.path.localeCompare(b.path)));
  assert.equal(events[1].meta.embedding_cache_hit,true);assert.equal(events[1].gemini_calls,1);
  assert.equal(events[0].meta.embedding_provider_calls,1);assert.equal(events[1].meta.embedding_provider_calls,0);assert.ok(events[1].meta.retrieval_ms>=0);
 }finally{globalThis.fetch=originalFetch;keys.forEach((k,i)=>saved[i]===undefined?Deno.env.delete(k):Deno.env.set(k,saved[i]!));}
});

Deno.test('independent retrieval starts early and video metadata does not wait for unrelated queries',async()=>{
 const keys=['GEMINI_API_KEY','SUPABASE_URL','SUPABASE_SERVICE_ROLE_KEY','SEMANTIC_SEARCH_SHARED_SECRET','SEMANTIC_SEARCH_DISABLED'];
 const saved=keys.map(k=>Deno.env.get(k)),originalFetch=globalThis.fetch;
 ['fixture-provider','https://fixture.supabase.co','fixture-service','fixture-semantic','0'].forEach((v,i)=>Deno.env.set(keys[i],v));
 let keywordStarted=false,embeddingCalls=0,generationCalls=0,sourceCalls=0,commentsStarted=false,lineStarted=false;
 const comments=Promise.withResolvers<Response>(),line=Promise.withResolvers<Response>();
 const release=()=>{comments.resolve(Response.json([{comment_id:'42',content:'same comment',similarity:0.9}]));line.resolve(Response.json([{id:'line',content:'same LINE',similarity:0.9}]))};
 let timer:ReturnType<typeof setTimeout>|undefined;
 globalThis.fetch=async(input,init)=>{
  const url=new URL(input instanceof Request?input.url:String(input));
  const body=typeof init?.body==='string'?JSON.parse(init.body):{};
  if(url.pathname.endsWith('/search_openchat_keyword')){keywordStarted=true;assert.deepEqual(body,{query_text:query.slice(0,80),match_count:20});return Response.json([]);}
  if(url.pathname.endsWith(':embedContent')){embeddingCalls++;assert.ok(keywordStarted,'keyword read starts before vector provider');return Response.json({embedding:{values:Array.from({length:768},(_,i)=>(i+1)/1000)}});}
  if(url.pathname.endsWith('/match_comments_semantic')){commentsStarted=true;return comments.promise;}
  if(url.pathname.endsWith('/match_openchat_semantic')){lineStarted=true;return line.promise;}
  if(url.pathname.endsWith('/match_chunks_semantic'))return Response.json([{chunk_key:'k',source_id:1,start_sec:61,content:'same video',similarity:0.9}]);
  if(url.pathname.endsWith('/knowledge_sources')){
   sourceCalls++;assert.ok(commentsStarted&&lineStarted,'all independent retrieval is running');
   // These requests cannot finish until metadata has started: catches serialization
   // without relying on a timing or percentage benchmark.
   release();return Response.json([{id:1,source_key:'s',title:'fixture video',video_url:'https://vimeo.com/123'}]);
  }
  if(url.pathname.endsWith(':generateContent')){generationCalls++;const prompt=body.contents[0].parts[0].text;for(const value of ['same comment','same video','same LINE'])assert.ok(prompt.includes(value));return Response.json({candidates:[{content:{parts:[{text:'answer (コミュニティ1、セミナー1、LINEオプチャ1)'}]}}]});}
  if(url.pathname.endsWith('/app_qa_search_events'))return Response.json([], {status:201});
  throw new Error('unexpected fixture request');
 };
 const query='parallel-fixture-'+crypto.randomUUID();
 try{
  const request=new Request('https://fixture.supabase.co/functions/v1/semantic-search',{method:'POST',headers:{'x-semantic-shared-secret':'fixture-semantic'},body:JSON.stringify({query})});
  const response=await Promise.race([handleSemanticSearch(request),new Promise<never>((_,reject)=>{timer=setTimeout(()=>{release();reject(new Error('retrieval pipeline remained serialized'));},2000)})]);
  assert.equal(response.status,200);const result=await response.json();
  assert.equal(embeddingCalls,1);assert.equal(generationCalls,1);assert.equal(sourceCalls,1);
  assert.equal(result.relatedComments[0].comment_id,'42');assert.equal(result.relatedChunks[0].chunk_key,'k');assert.equal(result.relatedOpenchat[0].id,'line');assert.equal(result.relatedSources[0].title,'fixture video');
  assert.deepEqual(result.referenceLabels,{comments:{'42':'コミュニティ1'},chunks:{k:'セミナー1'},openchats:{line:'LINEオプチャ1'}});
 }finally{clearTimeout(timer);release();globalThis.fetch=originalFetch;keys.forEach((k,i)=>saved[i]===undefined?Deno.env.delete(k):Deno.env.set(k,saved[i]!));}
});

Deno.test('failed LINE retrieval is explicit and cannot generate a silently incomplete answer',async()=>{
 const keys=['GEMINI_API_KEY','SUPABASE_URL','SUPABASE_SERVICE_ROLE_KEY','SEMANTIC_SEARCH_SHARED_SECRET','SEMANTIC_SEARCH_DISABLED'];
 const saved=keys.map(k=>Deno.env.get(k)),originalFetch=globalThis.fetch;
 ['fixture-provider','https://fixture.supabase.co','fixture-service','fixture-semantic','0'].forEach((v,i)=>Deno.env.set(keys[i],v));
 let failure='',generationCalls=0;const events:any[]=[];
 globalThis.fetch=async(input,init)=>{
  const url=new URL(input instanceof Request?input.url:String(input));
  if(url.pathname.endsWith(':embedContent'))return Response.json({embedding:{values:Array.from({length:768},(_,i)=>(i+1)/1000)}});
  if(url.pathname.endsWith(':generateContent')){generationCalls++;throw new Error('generation must not run');}
  if(url.pathname.endsWith('/'+failure))return Response.json({message:'fixture source unavailable',code:'fixture'}, {status:503});
  if(url.pathname.includes('/rpc/'))return Response.json([]);
  if(url.pathname.endsWith('/app_qa_search_events')){events.push(JSON.parse(String(init?.body)));return Response.json([], {status:201});}
  throw new Error('unexpected fixture request');
 };
 try{
  for(failure of ['match_openchat_semantic','search_openchat_keyword']){
   const response=await handleSemanticSearch(new Request('https://fixture.supabase.co/functions/v1/semantic-search',{method:'POST',headers:{'x-semantic-shared-secret':'fixture-semantic'},body:JSON.stringify({query:'failure-fixture-'+crypto.randomUUID()})}));
   assert.equal(response.status,500);assert.equal((await response.json()).code,'semantic_search_failed');
  }
  assert.equal(generationCalls,0);assert.equal(events.length,2);assert.ok(events.every(event=>event.result_status==='error'));
 }finally{globalThis.fetch=originalFetch;keys.forEach((k,i)=>saved[i]===undefined?Deno.env.delete(k):Deno.env.set(k,saved[i]!));}
});
