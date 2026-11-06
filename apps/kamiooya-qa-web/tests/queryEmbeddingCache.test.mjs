import test from 'node:test';
import assert from 'node:assert/strict';
import {createQueryEmbeddingCache,embeddingKey} from '../lib/queryEmbeddingCache.ts';
const tick=async()=>{for(let i=0;i<8;i++)await Promise.resolve();};
test('exact identical preprocessing is shared and returned vectors cannot mutate the cache',async()=>{
 const cache=createQueryEmbeddingCache(3);let calls=0,finish;
 const load=async()=>{calls++;return new Promise(r=>{finish=r;});};
 const a=cache.get('same',load),b=cache.get('same',load);await tick();assert.equal(calls,1);finish([0.1,0.2,0.3]);
 const [x,y]=await Promise.all([a,b]);assert.equal(x.cacheHit,false);assert.equal(y.cacheHit,true);assert.deepEqual(x.values,y.values);x.values[0]=999;
 assert.deepEqual((await cache.get('same',load)).values,[0.1,0.2,0.3]);assert.equal(calls,1);
});
test('one cancelled request cannot cancel another user of the same vector',async()=>{
 const cache=createQueryEmbeddingCache(3);let finish,upstreamSignal;
 const load=async signal=>{upstreamSignal=signal;return new Promise(r=>{finish=r;});};
 const first=new AbortController(),second=new AbortController();const a=cache.get('same',load,first.signal),b=cache.get('same',load,second.signal);const stopped=assert.rejects(a,e=>e.name==='AbortError');await tick();first.abort();await stopped;
 assert.equal(upstreamSignal.aborted,false);finish([1,2,3]);assert.deepEqual((await b).values,[1,2,3]);
});
test('when all consumers leave, unfinished preprocessing is cancelled and never reused',async()=>{
 const cache=createQueryEmbeddingCache(3);let signal;
 const load=s=>{signal=s;return new Promise((resolve,reject)=>s.addEventListener('abort',()=>reject(s.reason),{once:true}));};
 const c=new AbortController(),p=cache.get('same',load,c.signal),stopped=assert.rejects(p);await tick();c.abort();await stopped;assert.equal(signal.aborted,true);
 assert.equal((await cache.get('same',async()=>[1,2,3])).cacheHit,false);
});
test('failed or invalid vectors are not reused, and TTL/model/task/dimension/query boundaries are preserved',async()=>{
 let now=0,calls=0;const cache=createQueryEmbeddingCache(3,{now:()=>now,ttlMs:100});const load=async()=>{calls++;return [1,2,3];};
 await assert.rejects(cache.get('bad',async()=>[1,NaN,3]));await assert.rejects(cache.get('bad',async()=>[0,0,0]));await assert.rejects(cache.get('bad',async()=>[1]));
 await cache.get('same',load);now=99;assert.equal((await cache.get('same',load)).cacheHit,true);now=100;assert.equal((await cache.get('same',load)).cacheHit,false);assert.equal(calls,2);
 const variants=[['model','query',3,'質問'],['model2','query',3,'質問'],['model','document',3,'質問'],['model','query',4,'質問'],['model','query',3,'質問 ']];
 const keys=await Promise.all(variants.map(v=>embeddingKey(...v)));assert.equal(new Set(keys).size,variants.length);assert.match(keys[0],/^[0-9a-f]{64}$/);
});
test('bounded LRU does not evict an active shared request',async()=>{
 const cache=createQueryEmbeddingCache(3,{maxEntries:1});let calls=0,finish;const load=()=>{calls++;return new Promise(r=>{finish=r;});};
 const a=cache.get('a',load);await tick();await cache.get('b',async()=>[3,2,1]);const again=cache.get('a',load);await tick();assert.equal(calls,1);finish([1,2,3]);await Promise.all([a,again]);
});
