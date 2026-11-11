import test from 'node:test';
import assert from 'node:assert/strict';
import {findTroubledChats, similarity, summarizeSignals} from '../lib/conversationSignals.ts';
const t=(m)=>new Date(Date.UTC(2026,10,11,2,m)).toISOString();
const job=(chat,m,query,extra={})=>({user_id:'u1',chat_id:chat,mode:'semantic',query,status:'done',created_at:t(m),answer:'答え',...extra});
test('similar questions asked again soon count as a rephrase',()=>{
 assert.ok(similarity('バックファイナンスの取り組み方','バックファイナンスの取り組み方法は？')>0.45);
 const [c]=findTroubledChats([job('a',0,'バックファイナンスの取り組み方'),job('a',3,'バックファイナンスの取り組み方法は？')],[{chat_id:'a'}]);
 assert.deepEqual(c.turns[1].signals,['rephrase']);
});
test('follow-up wording and a deep retry are flagged on the later turn',()=>{
 const [c]=findTroubledChats([job('a',0,'バックファイナンスの取り組み方'),job('a',2,'法人での事例を詳しく教えて',{mode:'deep'})],[{chat_id:'a'}]);
 assert.deepEqual(c.turns[1].signals.sort(),['deep_retry','followup']);assert.equal(c.score,5);
});
test('refusals, failures, bad ratings and one-shot chats without source opens',()=>{
 const chats=findTroubledChats([
  job('r',0,'Xについて',{answer:'参照内で確証が取れないため、お答えすることができません。'}),
  job('f',0,'Yについて',{status:'failed',answer:null}),
  job('b',0,'Zについて'),job('b',30,'まったく別の話題です'),
  job('o',0,'Wについて'),
  job('ok',0,'Vについて'),
  job('run',0,'Uについて',{status:'running'}),
 ],[{chat_id:'ok'},{chat_id:'b'}],[{chat_id:'b',rating:'bad'}]);
 const by=Object.fromEntries(chats.map(c=>[c.chat_id,c.signals]));
 assert.deepEqual(by,{r:['refusal'],f:['failed'],b:['bad_rating'],o:['no_source_open']});
 assert.equal(chats[chats.length-1].chat_id,'o'); // 弱い目印は下
 assert.deepEqual(summarizeSignals(chats),{refusal:1,failed:1,bad_rating:1,no_source_open:1});
});
