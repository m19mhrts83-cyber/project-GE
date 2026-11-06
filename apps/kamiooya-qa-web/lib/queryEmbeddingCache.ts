// Worker-local preprocessing only. Answers and search results are never cached.
type Entry={promise:Promise<readonly number[]>;controller:AbortController;users:number;pending:boolean;expires:number};
export const embeddingKey=async(model:string,task:string,dimensions:number,query:string)=>
 Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(JSON.stringify([model,task,dimensions,query])))),b=>b.toString(16).padStart(2,'0')).join('');

export function createQueryEmbeddingCache(dimensions:number,options:{maxEntries?:number;ttlMs?:number;now?:()=>number}={}){
 const entries=new Map<string,Entry>(),max=options.maxEntries??64,ttl=options.ttlMs??180000,now=options.now??Date.now;
 const valid=(values:number[])=>{
  if(values.length!==dimensions||!values.every(Number.isFinite)||!values.some(v=>v!==0))throw new Error('invalid_query_embedding');
  return Object.freeze(values.slice());
 };
 return {
  async get(key:string,load:(signal:AbortSignal)=>Promise<number[]>,signal?:AbortSignal):Promise<{values:number[];cacheHit:boolean}>{
   signal?.throwIfAborted();
   for(const [k,e]of entries)if(!e.pending&&e.expires<=now())entries.delete(k);
   let entry=entries.get(key);const hit=!!entry;
   if(!entry){
    // Never evict a shared active request and accidentally start it twice.
    if(entries.size>=max){const oldest=[...entries].find(([,e])=>!e.pending);if(oldest)entries.delete(oldest[0]);}
    if(max<=0||entries.size>=max)return {values:[...valid(await load(signal??new AbortController().signal))],cacheHit:false};
    const controller=new AbortController();
    entry={controller,users:0,pending:true,expires:0,promise:Promise.resolve([])};
    const current=entry;entries.set(key,current);
    current.promise=Promise.resolve().then(()=>load(controller.signal)).then(values=>{
     const result=valid(values);current.pending=false;current.expires=now()+ttl;return result;
    }).catch(error=>{current.pending=false;if(entries.get(key)===current)entries.delete(key);throw error;});
   }else{entries.delete(key);entries.set(key,entry);}
   const current=entry;current.users++;let removeAbort=()=>{};
   try{
    const values=await new Promise<readonly number[]>((resolve,reject)=>{
     const abort=()=>reject(signal?.reason??new DOMException('Aborted','AbortError'));
     removeAbort=()=>signal?.removeEventListener('abort',abort);
     signal?.addEventListener('abort',abort,{once:true});
     current.promise.then(resolve,reject).finally(removeAbort);
     if(signal?.aborted)abort();
    });
    signal?.throwIfAborted();return {values:values.slice(),cacheHit:hit};
   }finally{
    removeAbort();current.users--;
    if(current.pending&&current.users===0){if(entries.get(key)===current)entries.delete(key);current.controller.abort();}
   }
  }
 };
}
