import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
import {labelAnswerSources,attachReferenceLabels,mentionedSourceLabels} from '../lib/searchReferences.ts';
const load=()=>vm.runInNewContext(readFileSync(new URL('../public/raimo/app.js',import.meta.url),'utf8')+'\nApp;',{
 document:{addEventListener(){},getElementById:()=>null},window:{setTimeout},console,URL,fetch,Intl,Date
});
test('published HTML does not suppress Raimo automatic app.js injection with a commented script tag',()=>{
 const html=readFileSync(new URL('../public/raimo/index.html',import.meta.url),'utf8');
 assert.equal(/<!--[\s\S]*?<script\s+src=["']app\.js["'][\s\S]*?-->/.test(html),false);
});
test('abbreviated answer markers retain their explicit context identities',()=>{
 assert.deepEqual([...mentionedSourceLabels('LINEオプチャ99',new Set(['LINEオプチャ1']))],[]);
 assert.deepEqual([...mentionedSourceLabels('LINEオプチャ1、4、7、8、10。コミュニティ2,5。セミナー3')],['LINEオプチャ1','LINEオプチャ4','LINEオプチャ7','LINEオプチャ8','LINEオプチャ10','コミュニティ2','コミュニティ5','セミナー3']);
 const app=load();const refs=app.buildCitationsFromRelated([],[],[],null,[{id:'four',citation_label:'LINEオプチャ4'}]);
 const linked=app.linkReferenceLabels('LINEオプチャ1、4、7',refs,'m');
 assert.ok(linked.includes('[LINEオプチャ4](#reference-m-openchat-four)'));
 assert.ok(linked.endsWith('LINEオプチャ7'));
});
test('a mentioned video title and position links directly to that position',()=>{
 const app=load();const linked=app.linkReferenceLabels('動画A 01:01頃を参照。',[{kind:'video_chunk',videoTitle:'動画A',videoUrl:'https://vimeo.com/123?h=fixture',startSec:61}],'m');
 assert.equal(linked,'[動画A 01:01頃](https://vimeo.com/123?h=fixture#t=61s)を参照。');
});
test('legacy reference recovery uses exact query and unique event time, including missing video metadata',async()=>{
 const app=load();app.authGatewayBase='https://gateway.example';app.state.currentUser={id:'one'};app.state.currentSessionId='mine';app.state.messageLoadGeneration=1;
 app.state.chatMessages=[{id:'u',role:'user',content:'question',created_at:'2026-11-05T12:00:00Z'},{id:'a',role:'assistant',content:'LINEオプチャ1',created_at:'2026-11-05T12:01:00Z'}];
 app.state.citationsByMessageId={a:[{kind:'openchat',openchatId:'line'}]};app.renderChatMessages=()=>{};
 app.saveCitationsForMessage=(sid,id,refs)=>{app.state.citationsByMessageId[id]=refs;};
 const event={created_at:'2026-11-05T12:00:59Z',query_text:'question',used_sources:{comment_ids:[],chunk_keys:['video'],openchat_ids:['line']}};
 app.apiClient=async()=>({events:[event],chunks:[{chunk_key:'video',source_id:7,start_sec:61,content:'video passage'}],sources:[{id:7,source_key:'s',title:'動画A',video_url:'https://vimeo.com/123'}]});
 await app.hydrateHistoricalReferences('mine',1);
 assert.equal(app.state.citationsByMessageId.a[0].citationLabel,'LINEオプチャ1');assert.equal(app.state.citationsByMessageId.a[1].citationLabel,'セミナー1');assert.match(app.state.citationsByMessageId.a[1].videoUrl,/#t=61s$/);
 app.state.citationsByMessageId={a:[{kind:'openchat',openchatId:'line'}]};app.apiClient=async()=>({events:[event,event],sources:[]});await app.hydrateHistoricalReferences('mine',1);
 assert.equal(app.state.citationsByMessageId.a[0].citationLabel,undefined);
});
test('answer context source labels survive client recency reordering',()=>{
 const labels=labelAnswerSources([{comment_id:'old'},{comment_id:'new'}], [{chunk_key:'video'}],[{id:'line-old'},{id:'line-new'}]);
 const reordered=attachReferenceLabels([{id:'line-new'},{id:'line-old'}],'id',labels.openchats);
 assert.deepEqual(reordered.map(r=>r.citation_label),['LINEオプチャ2','LINEオプチャ1']);
 const app=load();const c=app.buildCitationsFromRelated([],[],[],null,reordered);
 const html=app.renderCitationsPanel(c,'message-1');
 assert.ok(html.includes('[LINEオプチャ1]'));assert.ok(html.includes('[LINEオプチャ2]'));
 const linked=app.linkReferenceLabels('LINEオプチャ1、LINEオプチャ2、LINEオプチャ10',c,'message-1');
 assert.ok(linked.includes('[LINEオプチャ1](#reference-message-1-openchat-line-old)'));
 assert.ok(linked.endsWith('LINEオプチャ10'));
});
test('calendar grouping uses JST, this year by month and older years, newest first',()=>{
 const app=load();const groups=app.groupReferencesByDate([
  {postedAt:'2026-01-02T00:00:00+09:00'}, {postedAt:'2025-12-31T15:01:00Z'},
  {postedAt:'2026-11-04T12:00:00+09:00'}, {postedAt:'2025-08-01T00:00:00Z'}, {postedAt:''}
 ],2026);
 assert.deepEqual(Array.from(groups,g=>g.label),['2026年11月','2026年1月','2025年','日時未記録']);
 assert.equal(groups[1].items.length,2);
});
test('missing dates are hydrated by exact comment id, never by ingestion date',()=>{
 const app=load();app.state.referenceComments={'42':{posted_at:'2026-11-03T00:00:00Z'}};
 assert.equal(app.resolveCommentPostedAt({comment_id:'42'}),'2026-11-03T00:00:00Z');
 assert.equal(app.resolveCommentPostedAt({comment_id:'43',created_at:'2026-11-03'}),'');
 assert.equal(app.resolveCommentPostedAt({comment_id:'42',posted_at:'2025-01-02'}),'2025-01-02');
});
test('each video citation opens its exact Vimeo timestamp and cannot use script URLs',()=>{
 const app=load();app.state.knowledgeSources={v:{id:7,source_key:'v',title:'動画A',video_url:'https://vimeo.com/123?h=fixture'}};
 const rows=[{chunk_key:'k1',source_id:7,start_sec:61,content:'a',citation_label:'セミナー1'}, {chunk_key:'k2',source_id:7,start_sec:152,content:'b',citation_label:'セミナー2'}];
 const c=app.buildCitationsFromRelated([],rows,[],null,[]);const html=app.renderCitationsPanel(c,'m');
 assert.ok(html.includes('01:01'));assert.ok(html.includes('02:32'));assert.ok(html.includes('#t=61s'));assert.ok(html.includes('#t=152s'));
 assert.ok(html.includes('[セミナー1]'));assert.ok(html.includes('[セミナー2]'));assert.ok(html.includes('動画A'));
 assert.equal(app.withVideoTimeUrl('javascript:alert(1)',20),'');
 assert.equal(app.withVideoTimeUrl('https://vimeo.com/123?t=2#t=2s',40),'https://vimeo.com/123#t=40s');
});
test('attachment pages retry a transient read without duplicating records or retaining passwords',async()=>{
 const app=load();app.authGatewayBase='https://gateway.example';app.state.currentUser={id:'one'};app.state.attachmentGeneration=1;
 app.renderChatMessages=()=>{};app.renderCommentTable=()=>{};app.retryDelay=async()=>{};
 let calls=0;app.apiClient=async()=>({token:'fixture-session'});app.attachmentRequest=async(body)=>{
  if(calls++===0){const e=new Error('temporary');e.httpStatus=503;throw e;}
  return {attachments:[{id:'a',comment_id:'12'}],next_offset:null};
 };
 await app.initializeAttachments('mail','not-retained',1);
 assert.equal(calls,2);assert.equal(app.state.attachmentIndex['12'].length,1);assert.equal(app.state.attachmentStatus,'');assert.equal(app.state.attachmentLoading,false);
 assert.equal(JSON.stringify(app.state).includes('not-retained'),false);
});
test('attachment permission errors are not retried and leave a recoverable status',async()=>{
 const app=load();app.authGatewayBase='https://gateway.example';app.state.currentUser={id:'one'};app.state.attachmentGeneration=1;let calls=0;
 app.apiClient=async()=>({token:'fixture'});app.attachmentRequest=async()=>{calls++;const e=new Error('denied');e.httpStatus=401;throw e;};
 await app.initializeAttachments('','',1);assert.equal(calls,1);assert.match(app.state.attachmentStatus,/ログイン/);assert.equal(app.state.attachmentLoading,false);
});
