import assert from 'node:assert/strict';
import {handleSemanticSearch,openchatThreadLabel,threadHeading,normalizeHistory,contextualSearchQuery,buildAnswerPrompt,buildPlanPrompt,parsePlan,clarificationAnswer,CLARIFY_MARK} from './handler.ts';

Deno.test('LINE filename browse and exact attachment source reads use ready rows without AI calls',async()=>{
 const keys=['GEMINI_API_KEY','SUPABASE_URL','SUPABASE_SERVICE_ROLE_KEY','QA_OPS_SERVER_SECRET','SEMANTIC_SEARCH_DISABLED'];
 const saved=keys.map(k=>Deno.env.get(k)),originalFetch=globalThis.fetch;
 ['fixture','https://fixture.supabase.co','fixture-service','fixture-ops-secret-0123456789abcdef','0'].forEach((v,i)=>Deno.env.set(keys[i],v));
 const id='oc_'+'a'.repeat(64),reads:URL[]=[];
 globalThis.fetch=async(input)=>{
  const url=new URL(input instanceof Request?input.url:String(input));
  if(url.pathname.endsWith('/line_openchat_logs')){
   reads.push(url);assert.equal(url.searchParams.get('ingest_status'),'eq.ready');
   return Response.json([{id,chat_title:'修繕',content:'【LINE添付・内容未解析】見積,改訂.pdf',posted_at:null}]);
  }
  if(url.pathname.endsWith('/app_qa_search_events'))return Response.json([],{status:201});
  throw new Error('unexpected network/AI request');
 };
 try{
  const call=(body:unknown)=>handleSemanticSearch(new Request('https://fixture.supabase.co/functions/v1/semantic-search',{
   method:'POST',headers:{'x-qa-ops-secret':'fixture-ops-secret-0123456789abcdef'},body:JSON.stringify(body)}));
  let r=await call({list_openchat:true,query:'見積,改訂.pdf',only_attachments:true});
  assert.equal(r.status,200);assert.equal((await r.json()).relatedOpenchat[0].id,id);
  assert.equal(reads[0].searchParams.get('source_system'),'eq.line_openchat_attachment');
  assert.ok(reads[0].searchParams.get('or')?.includes('content.ilike."%見積,改訂.pdf%"'));
  r=await call({list_openchat:true,openchat_id:id,query:id});
  assert.equal(r.status,200);assert.equal((await r.json()).relatedOpenchat[0].id,id);
  assert.equal(reads[1].searchParams.get('id'),'eq.'+id);
 }finally{globalThis.fetch=originalFetch;keys.forEach((k,i)=>saved[i]===undefined?Deno.env.delete(k):Deno.env.set(k,saved[i]!));}
});

Deno.test('cached query vectors still retrieve fresh sources and generate each answer with unchanged evidence',async()=>{
 const keys=['GEMINI_API_KEY','SUPABASE_URL','SUPABASE_SERVICE_ROLE_KEY','QA_OPS_SERVER_SECRET','SEMANTIC_SEARCH_DISABLED'];
 const saved=keys.map(k=>Deno.env.get(k)),originalFetch=globalThis.fetch;
 const fixtures=['fixture-provider','https://fixture.supabase.co','fixture-service','fixture-ops-secret-0123456789abcdef','0'];
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
  const request=()=>new Request('https://fixture.supabase.co/functions/v1/semantic-search',{method:'POST',headers:{'x-qa-ops-secret':'fixture-ops-secret-0123456789abcdef'},body:JSON.stringify({query})});
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
 const keys=['GEMINI_API_KEY','SUPABASE_URL','SUPABASE_SERVICE_ROLE_KEY','QA_OPS_SERVER_SECRET','SEMANTIC_SEARCH_DISABLED'];
 const saved=keys.map(k=>Deno.env.get(k)),originalFetch=globalThis.fetch;
 ['fixture-provider','https://fixture.supabase.co','fixture-service','fixture-ops-secret-0123456789abcdef','0'].forEach((v,i)=>Deno.env.set(keys[i],v));
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
  const request=new Request('https://fixture.supabase.co/functions/v1/semantic-search',{method:'POST',headers:{'x-qa-ops-secret':'fixture-ops-secret-0123456789abcdef'},body:JSON.stringify({query})});
  const response=await Promise.race([handleSemanticSearch(request),new Promise<never>((_,reject)=>{timer=setTimeout(()=>{release();reject(new Error('retrieval pipeline remained serialized'));},2000)})]);
  assert.equal(response.status,200);const result=await response.json();
  assert.equal(embeddingCalls,1);assert.equal(generationCalls,1);assert.equal(sourceCalls,1);
  assert.equal(result.relatedComments[0].comment_id,'42');assert.equal(result.relatedChunks[0].chunk_key,'k');assert.equal(result.relatedOpenchat[0].id,'line');assert.equal(result.relatedSources[0].title,'fixture video');
  assert.deepEqual(result.referenceLabels,{comments:{'42':'コミュニティ1'},chunks:{k:'セミナー1'},openchats:{line:'LINEオプチャ1'}});
 }finally{clearTimeout(timer);release();globalThis.fetch=originalFetch;keys.forEach((k,i)=>saved[i]===undefined?Deno.env.delete(k):Deno.env.set(k,saved[i]!));}
});

Deno.test('failed LINE retrieval is explicit and cannot generate a silently incomplete answer',async()=>{
 const keys=['GEMINI_API_KEY','SUPABASE_URL','SUPABASE_SERVICE_ROLE_KEY','QA_OPS_SERVER_SECRET','SEMANTIC_SEARCH_DISABLED'];
 const saved=keys.map(k=>Deno.env.get(k)),originalFetch=globalThis.fetch;
 ['fixture-provider','https://fixture.supabase.co','fixture-service','fixture-ops-secret-0123456789abcdef','0'].forEach((v,i)=>Deno.env.set(keys[i],v));
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
   const response=await handleSemanticSearch(new Request('https://fixture.supabase.co/functions/v1/semantic-search',{method:'POST',headers:{'x-qa-ops-secret':'fixture-ops-secret-0123456789abcdef'},body:JSON.stringify({query:'failure-fixture-'+crypto.randomUUID()})}));
   assert.equal(response.status,500);assert.equal((await response.json()).code,'semantic_search_failed');
  }
  assert.equal(generationCalls,0);assert.equal(events.length,2);assert.ok(events.every(event=>event.result_status==='error'));
 }finally{globalThis.fetch=originalFetch;keys.forEach((k,i)=>saved[i]===undefined?Deno.env.delete(k):Deno.env.set(k,saved[i]!));}
});

Deno.test('chat_context: previous turns steer the search text and the answer prompt',()=>{
 const history=normalizeHistory([{question:'外壁塗装の時期は？',answer:'10〜15年が目安'},{question:''},'bad',{question:'x'.repeat(900),answer:'y'.repeat(3000)}]);
 assert.equal(history.length,2);assert.equal(history[1].question.length,500);assert.equal(history[1].answer.length,1500);
 assert.equal(contextualSearchQuery('また詳しく',[]),'また詳しく');
 const q=contextualSearchQuery('また詳しく調べて',[{question:'外壁塗装の時期は？',answer:''}]);
 assert.ok(q.startsWith('外壁塗装の時期は？'));assert.ok(q.endsWith('また詳しく調べて'));
 const prompt=buildAnswerPrompt('また詳しく調べて','[コミュニティ1] 外壁',[{question:'外壁塗装の時期は？',answer:'10〜15年が目安'}]);
 assert.ok(prompt.includes('(1) 質問: 外壁塗装の時期は？'));assert.ok(prompt.includes('直前の質問のテーマ'));
 assert.ok(!buildAnswerPrompt('外壁','[コミュニティ1] 外壁').includes('これまでのやり取り'));
});

Deno.test('clarify: rewrite fills omitted topics, asks back at most once in a row',()=>{
 const h=[{question:'バックファイナンスの取り組み方',answer:'銀行に…'}];
 const p=buildPlanPrompt('法人での事例を詳しく教えて',h,true);
 assert.ok(p.includes('(1) 質問: バックファイナンスの取り組み方'));assert.ok(p.includes('action を ask'));
 assert.ok(buildPlanPrompt('x',h,false).includes('今回は聞き返さない'));
 const s=parsePlan('{"action":"search","search_query":"法人でのバックファイナンスの事例"}','法人での事例',true);
 assert.deepEqual(s,{action:'search',searchQuery:'法人でのバックファイナンスの事例',ask:'',options:[]});
 const a=parsePlan('```json\n{"action":"ask","search_query":"事例","ask":"どの事例ですか？","options":["法人の融資","個人の融資"]}\n```','事例',true);
 assert.equal(a?.action,'ask');assert.deepEqual(a?.options,['法人の融資','個人の融資']);
 assert.equal(parsePlan('{"action":"ask","search_query":"事例","ask":"どの？"}','事例',false)?.action,'search'); // 続けて聞き返さない
 assert.equal(parsePlan('not json','q',true),null);
 assert.equal(parsePlan('{"action":"search"}','元の質問',true)?.searchQuery,'元の質問');
 const text=clarificationAnswer(a!);assert.ok(text.startsWith(CLARIFY_MARK+'どの事例ですか？'));assert.ok(text.includes('1. 法人の融資'));
});

Deno.test('openchat thread numbers: list attaches numbers, thread mode reads one thread oldest first',async()=>{
 const keys=['GEMINI_API_KEY','SUPABASE_URL','SUPABASE_SERVICE_ROLE_KEY','QA_OPS_SERVER_SECRET','SEMANTIC_SEARCH_DISABLED'];
 const saved=keys.map(k=>Deno.env.get(k)),originalFetch=globalThis.fetch;
 ['fixture','https://fixture.supabase.co','fixture-service','fixture-ops-secret-0123456789abcdef','0'].forEach((v,i)=>Deno.env.set(keys[i],v));
 const logs:URL[]=[],threads:URL[]=[];
 const row={id:'oc_1',chat_title:'30空室相談G',stream_type:'thread',thread_title:'t013e392',content:'返信です',posted_at:'2026-11-01T00:00:00Z'};
 globalThis.fetch=async(input)=>{
  const url=new URL(input instanceof Request?input.url:String(input));
  if(url.pathname.endsWith('/qa_openchat_threads')){threads.push(url);
   return Response.json([{chat_title:'30空室相談G',thread_key:'t013e392',thread_no:12,first_snippet:'東北の学生向けアパートの相談',first_sender:'A',post_count:3}]);}
  if(url.pathname.endsWith('/line_openchat_logs')){logs.push(url);return Response.json([row]);}
  if(url.pathname.endsWith('/app_qa_search_events'))return Response.json([],{status:201});
  throw new Error('unexpected network/AI request');
 };
 try{
  const call=(body:unknown)=>handleSemanticSearch(new Request('https://fixture.supabase.co/functions/v1/semantic-search',{
   method:'POST',headers:{'x-qa-ops-secret':'fixture-ops-secret-0123456789abcdef'},body:JSON.stringify(body)}));
  // スイッチ未指定なら番号を引かない（従来どおり）
  let r=await call({list_openchat:true});
  let j=await r.json();assert.equal(r.status,200);assert.equal(threads.length,0);assert.equal(j.relatedOpenchat[0].thread_no??null,null);
  // with_threads で番号と見出しを付ける
  r=await call({list_openchat:true,with_threads:true});j=await r.json();
  assert.equal(j.relatedOpenchat[0].thread_no,12);assert.equal(j.relatedOpenchat[0].thread_heading,'東北の学生向けアパートの相談');
  // 番号を押したとき: そのスレッドだけ古い順
  r=await call({list_openchat:true,with_threads:true,chat_title:'30空室相談G',thread_no:12});j=await r.json();
  assert.equal(j.meta.mode,'thread');assert.equal(j.meta.thread.thread_no,12);assert.equal(j.relatedOpenchat.length,1);
  const last=logs[logs.length-1];
  assert.equal(last.searchParams.get('thread_title'),'eq.t013e392');assert.equal(last.searchParams.get('stream_type'),'eq.thread');
  assert.equal(last.searchParams.get('ingest_status'),'eq.ready');assert.ok(last.searchParams.get('order')?.startsWith('posted_at.asc'));
 }finally{globalThis.fetch=originalFetch;keys.forEach((k,i)=>saved[i]===undefined?Deno.env.delete(k):Deno.env.set(k,saved[i]!));}
});

Deno.test('openchat thread label uses number, then readable title',()=>{
 assert.equal(openchatThreadLabel({thread_no:5,thread_title:'t013e392'}),'スレッド5');
 assert.equal(openchatThreadLabel({thread_no:null,thread_title:'物件名の相談'}),'物件名の相談');
});

Deno.test('openchat thread roots: thread view starts with the root post, root main rows get the thread number',async()=>{
 const keys=['GEMINI_API_KEY','SUPABASE_URL','SUPABASE_SERVICE_ROLE_KEY','QA_OPS_SERVER_SECRET','SEMANTIC_SEARCH_DISABLED'];
 const saved=keys.map(k=>Deno.env.get(k)),originalFetch=globalThis.fetch;
 ['fixture','https://fixture.supabase.co','fixture-service','fixture-ops-secret-0123456789abcdef','0'].forEach((v,i)=>Deno.env.set(keys[i],v));
 const info={chat_title:'20戸建G',thread_key:'「t1949673…」',thread_no:7,first_snippet:'近隣の月極駐車場を借りて',first_sender:'A',post_count:2,
  root_text:'物件名変えてリニューアル募集したら、２日で申し込み入りました',root_posted_at:'2026-11-17T07:53:07Z',root_sender:'柴田',root_log_id:'oc_root',root_status:'matched'};
 const rootRow={id:'oc_root',chat_title:'20戸建G',stream_type:'main',thread_title:null,content:info.root_text,posted_at:'2026-11-17T07:53:00Z',sender_name:'柴田'};
 const reply={id:'oc_r1',chat_title:'20戸建G',stream_type:'thread',thread_title:'「t1949673…」',content:'おめでとうございます',posted_at:'2026-11-17T09:00:00Z'};
 let rootLinked=true;
 globalThis.fetch=async(input)=>{
  const url=new URL(input instanceof Request?input.url:String(input));
  if(url.pathname.endsWith('/qa_openchat_threads')){
   if(url.searchParams.get('root_log_id'))return Response.json(url.searchParams.get('root_log_id')!.includes('oc_root')?[info]:[]);
   return Response.json([rootLinked?info:{...info,root_log_id:null}]);}
  if(url.pathname.endsWith('/line_openchat_logs')){
   if(url.searchParams.get('id')==='eq.oc_root')return Response.json([rootRow]);
   if(url.searchParams.get('stream_type')==='eq.thread')return Response.json([reply]);
   return Response.json([rootRow,reply]);}
  if(url.pathname.endsWith('/app_qa_search_events'))return Response.json([],{status:201});
  throw new Error('unexpected network/AI request');
 };
 try{
  const call=(body:unknown)=>handleSemanticSearch(new Request('https://fixture.supabase.co/functions/v1/semantic-search',{
   method:'POST',headers:{'x-qa-ops-secret':'fixture-ops-secret-0123456789abcdef'},body:JSON.stringify(body)}));
  // 一覧: 元の投稿（メイン）にも番号が付き、見出しは元の投稿の書き出し
  let j=await (await call({list_openchat:true,with_threads:true})).json();
  const main=j.relatedOpenchat.find((r:{id:string})=>r.id==='oc_root');const th=j.relatedOpenchat.find((r:{id:string})=>r.id==='oc_r1');
  assert.equal(main.thread_no,7);assert.equal(main.is_thread_root,true);
  assert.equal(th.thread_no,7);assert.equal(th.thread_heading,info.root_text);
  // スレッドを開く: 先頭が元の投稿、続いてスレッドの書き込み
  j=await (await call({list_openchat:true,with_threads:true,chat_title:'20戸建G',thread_no:7})).json();
  assert.deepEqual(j.relatedOpenchat.map((r:{id:string})=>r.id),['oc_root','oc_r1']);assert.equal(j.relatedOpenchat[0].is_thread_root,true);
  // DB のメイン投稿と結べていないときは LINE から取った本文で先頭に出す
  rootLinked=false;
  j=await (await call({list_openchat:true,with_threads:true,chat_title:'20戸建G',thread_no:7})).json();
  assert.equal(j.relatedOpenchat.length,2);assert.equal(j.relatedOpenchat[0].id,'');assert.equal(j.relatedOpenchat[0].content,info.root_text);
  assert.equal(j.relatedOpenchat[0].is_thread_root,true);
 }finally{globalThis.fetch=originalFetch;keys.forEach((k,i)=>saved[i]===undefined?Deno.env.delete(k):Deno.env.set(k,saved[i]!));}
});

Deno.test('openchat thread heading: thread name, then root post, then first reply',()=>{
 assert.equal(threadHeading({thread_key:'「物件名の相談」',root_text:'元の投稿',first_snippet:'返信'}),'物件名の相談');
 assert.equal(threadHeading({thread_key:'「t1949673…」',root_text:'@講師きむら  物件名を\n変えました',first_snippet:'返信'}),'物件名を 変えました');
 assert.equal(threadHeading({thread_key:'「t1949673…」',root_text:null,first_snippet:'返信'}),'返信');
 assert.equal(openchatThreadLabel({thread_no:7,thread_title:null,thread_heading:'物件名変えて募集',is_thread_root:true}),'スレッド7「物件名変えて募集」の元の投稿');
});

Deno.test('server-only access: no key, a member-side legacy key for AI answers, and body/query secrets are refused',async()=>{
 const keys=['GEMINI_API_KEY','SUPABASE_URL','SUPABASE_SERVICE_ROLE_KEY','QA_OPS_SERVER_SECRET','RAIMO_AUTH_GATEWAY_SECRET','SEMANTIC_SEARCH_SHARED_SECRET','SEMANTIC_SEARCH_DISABLED'];
 const saved=keys.map(k=>Deno.env.get(k)),originalFetch=globalThis.fetch;
 const ops='fixture-ops-secret-0123456789abcdef',gateway='g'.repeat(40),legacy='legacy-browser-key-0123456789abcdef';
 ['fixture','https://fixture.supabase.co','fixture-service',ops,gateway,legacy,'0'].forEach((v,i)=>Deno.env.set(keys[i],v));
 globalThis.fetch=async(input)=>{
  const url=new URL(input instanceof Request?input.url:String(input));
  if(url.pathname.endsWith('/qa_feature_flags'))return Response.json([]);
  if(url.pathname.endsWith('/line_openchat_logs'))return Response.json([]);
  if(url.pathname.endsWith('/app_qa_search_events'))return Response.json([],{status:201});
  throw new Error('unexpected network/AI request');
 };
 try{
  const call=(headers:Record<string,string>,body:Record<string,unknown>)=>handleSemanticSearch(new Request('https://fixture.supabase.co/functions/v1/semantic-search',{method:'POST',headers,body:JSON.stringify(body)}));
  assert.equal((await call({},{query:'x'})).status,403);
  assert.equal((await call({},{query:'x',secret:ops})).status,403);
  assert.equal((await call({'x-semantic-shared-secret':legacy},{query:'x'})).status,403);
  assert.equal((await call({'x-gateway-proof':'wrong'},{list_openchat:true,query:''})).status,403);
  assert.equal((await call({'x-gateway-proof':gateway},{list_openchat:true,query:''})).status,200);
  assert.equal((await call({'x-qa-ops-secret':ops},{list_openchat:true,query:''})).status,200);
  // 移行中だけ: 旧画面のオプチャ一覧（AI を使わない）は旧い鍵で通る。Secrets から消せば閉じる。
  assert.equal((await call({'x-semantic-shared-secret':legacy},{list_openchat:true,query:''})).status,200);
  Deno.env.delete('SEMANTIC_SEARCH_SHARED_SECRET');
  assert.equal((await call({'x-semantic-shared-secret':legacy},{list_openchat:true,query:''})).status,403);
  Deno.env.set('QA_OPS_SERVER_SECRET','short');
  assert.equal((await call({'x-qa-ops-secret':'short'},{list_openchat:true,query:''})).status,403);
 }finally{globalThis.fetch=originalFetch;keys.forEach((k,i)=>saved[i]===undefined?Deno.env.delete(k):Deno.env.set(k,saved[i]!));}
});
