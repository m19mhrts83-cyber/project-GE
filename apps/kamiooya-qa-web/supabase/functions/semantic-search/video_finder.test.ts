import assert from 'node:assert/strict';
import {handleSemanticSearch,videoFinderKeywords,rankVideoMatches,videoFinderHeader,fixLoanMishearing} from './handler.ts';

Deno.test('video finder picks the topic word from "find a lesson video" questions only',()=>{
 assert.deepEqual(videoFinderKeywords('公庫について解説している講座の動画を探して'),['公庫']);
 assert.deepEqual(videoFinderKeywords('公庫の講座はありますか？'),['公庫']);
 assert.deepEqual(videoFinderKeywords('火災保険や修繕の動画を教えて'),['火災保険','修繕']);
 assert.equal(videoFinderKeywords('公庫の金利は何％ですか'),null);
 assert.equal(videoFinderKeywords('動画'),null);
});

Deno.test('title matches put dedicated lessons before group consulting, with lesson links',()=>{
 const rows=[
  {id:190,title:'2026年2月22日グルコン【公庫の基本を知る、公庫融資の現状と使い方2026～】（動画1169780137）',meta_json:{course:'神大家4.グルコン',lesson_url:'https://westudy.co.jp/lesson/lesson-20260222_groupconsulting'}},
  {id:116,title:'【実践】公庫融資の現状と使い方2026～（動画1169781052）',meta_json:{course:'神大家2.応用',lesson_url:'https://westudy.co.jp/lesson/genjyo_kouko_2026'}},
  {id:115,title:'【実践】公庫の基本を知る（動画1169781020）',meta_json:JSON.stringify({course:'神大家2.応用',lesson_url:'https://westudy.co.jp/lesson/kihon_kouko'})},
  {id:300,title:'【実践】銀行の選び方',meta_json:{course:'神大家2.応用'}},
 ];
 const m=rankVideoMatches(rows,['公庫']);
 assert.deepEqual(m.map(x=>x.id),[115,116,190]);
 const h=videoFinderHeader(m,['公庫']);
 assert.ok(h.startsWith('**「公庫」がタイトルに入っている講座動画**'));
 assert.ok(h.includes('1. [【実践】公庫の基本を知る](https://westudy.co.jp/lesson/kihon_kouko)（神大家2.応用）'));
 assert.ok(!h.includes('動画1169781020'));
 assert.equal(videoFinderHeader([],['公庫']),'');
});

Deno.test('高校 is read as 公庫 only inside loan talk',()=>{
 assert.equal(fixLoanMishearing('高校の融資制度について'),'公庫の融資制度について');
 assert.equal(fixLoanMishearing('高校生向けの物件で融資を受けた'),'高校生向けの物件で融資を受けた');
 assert.equal(fixLoanMishearing('近くに高校がある物件'),'近くに高校がある物件');
});

Deno.test('a "find the 公庫 lesson video" question lists title matches first and feeds their transcript to the answer',async()=>{
 const keys=['GEMINI_API_KEY','SUPABASE_URL','SUPABASE_SERVICE_ROLE_KEY','SEMANTIC_SEARCH_SHARED_SECRET','SEMANTIC_SEARCH_DISABLED'];
 const saved=keys.map(k=>Deno.env.get(k)),originalFetch=globalThis.fetch;
 ['fixture-provider','https://fixture.supabase.co','fixture-service','fixture-semantic','0'].forEach((v,i)=>Deno.env.set(keys[i],v));
 const prompts:string[]=[],events:any[]=[];
 globalThis.fetch=async(input,init)=>{
  const url=new URL(input instanceof Request?input.url:String(input));
  const body=typeof (init as any)?.body==='string'?JSON.parse((init as any).body):{};
  if(url.pathname.endsWith(':embedContent'))return Response.json({embedding:{values:Array.from({length:768},(_,i)=>(i+1)/1000)}});
  if(url.pathname.endsWith(':generateContent')){prompts.push(body.contents[0].parts[0].text);return Response.json({candidates:[{content:{parts:[{text:'公庫の基本を知るでは制度の全体を話しています（セミナー1）'}]}}]});}
  if(url.pathname.endsWith('/rpc/match_chunks_semantic'))return Response.json([{chunk_key:'other',source_id:9,start_sec:0,content:'グルコンで少し公庫の話',similarity:0.5}]);
  if(url.pathname.includes('/rpc/'))return Response.json([]);
  if(url.pathname.endsWith('/knowledge_sources')){
   if(url.searchParams.get('or'))return Response.json([{id:115,source_key:'westudy:kihon_kouko',title:'【実践】公庫の基本を知る（動画1169781020）',meta_json:{course:'神大家2.応用',lesson_url:'https://westudy.co.jp/lesson/kihon_kouko'}}]);
   return Response.json([{id:9,source_key:'g',title:'グルコン'}]);
  }
  if(url.pathname.endsWith('/knowledge_chunks')){assert.equal(url.searchParams.get('source_id'),'in.(115)');return Response.json([{chunk_key:'k0',source_id:115,start_sec:0,content:'高校の基本を知る 高校の融資制度について'},{chunk_key:'k1',source_id:115,start_sec:85,content:'設備資金と運転資金'},{chunk_key:'k2',source_id:115,start_sec:169,content:'三つ目'}]);}
  if(url.pathname.endsWith('/app_qa_search_events')){events.push(body);return Response.json([],{status:201});}
  throw new Error('unexpected '+url.pathname);
 };
 try{
  const r=await handleSemanticSearch(new Request('https://fixture.supabase.co/functions/v1/semantic-search',{method:'POST',headers:{'x-semantic-shared-secret':'fixture-semantic'},body:JSON.stringify({query:'公庫について解説している講座の動画を探して',video_finder:true})}));
  assert.equal(r.status,200);const out=await r.json();
  assert.ok(out.answer.startsWith('**「公庫」がタイトルに入っている講座動画**\n1. [【実践】公庫の基本を知る](https://westudy.co.jp/lesson/kihon_kouko)（神大家2.応用）'));
  assert.ok(out.answer.endsWith('公庫の基本を知るでは制度の全体を話しています（セミナー1）'));
  assert.ok(prompts[0].includes('[講座一覧]'));
  assert.ok(prompts[0].includes('[セミナー1] chunk=k0 title=【実践】公庫の基本を知る'));
  assert.ok(prompts[0].includes('公庫の基本を知る 公庫の融資制度'));
  assert.ok(!prompts[0].includes('chunk=k2'));
  assert.ok(out.relatedSources.some((s:any)=>s.id===115));
  assert.deepEqual(events[0].meta.video_finder,{keywords:['公庫'],matched:[115]});
  const off=await (await handleSemanticSearch(new Request('https://fixture.supabase.co/functions/v1/semantic-search',{method:'POST',headers:{'x-semantic-shared-secret':'fixture-semantic'},body:JSON.stringify({query:'公庫について解説している講座の動画を探して'})}))).json();
  assert.equal(off.answer,'公庫の基本を知るでは制度の全体を話しています（セミナー1）');
  assert.ok(!prompts[1].includes('[講座一覧]'));assert.equal(events[1].meta.video_finder,undefined);
 }finally{globalThis.fetch=originalFetch;keys.forEach((k,i)=>saved[i]===undefined?Deno.env.delete(k):Deno.env.set(k,saved[i]!));}
});
