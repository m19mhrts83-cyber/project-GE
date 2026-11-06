export type AnswerActor = {id:string;authVersion:string;sessionRef:string};
export type AnswerMode = 'normal'|'semantic'|'fast';
export type AnswerJob = {
 id:string;user_id:string;chat_id:string;request_id:string;request_hash:string;auth_version:string;parent_session_ref:string;
 mode:AnswerMode;query:string;status:'running'|'done'|'failed';deadline_at:string;result?:unknown;error_code?:string;
};
export type AnswerJobStore = {
 admit(input:Omit<AnswerJob,'id'|'status'>):Promise<{job?:AnswerJob;created?:boolean;busy?:boolean;conflict?:boolean}>;
 get(id:string,userId:string,chatId:string):Promise<AnswerJob|null>;
 finish(id:string,result:unknown,error?:string):Promise<void>;
};
export class AnswerJobError extends Error {code:string;status:number;constructor(code:string,status=400){super(code);this.code=code;this.status=status;}}
export const ANSWER_BUDGET_MS=300000;
const uuid=/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const hash=async(value:string)=>Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(value))),b=>b.toString(16).padStart(2,'0')).join('');

export function createAnswerJobs(d:{
 store:AnswerJobStore;schedule(task:Promise<void>):void;authorize(job:AnswerJob):Promise<boolean>;
 execute(job:AnswerJob,signal:AbortSignal):Promise<unknown>;now?:()=>number;timeout?:(ms:number)=>AbortSignal;
}){
 const now=d.now||Date.now, timeout=d.timeout||AbortSignal.timeout.bind(AbortSignal);
 const visible=(job:AnswerJob)=>({job_id:job.id,status:job.status,...(job.status==='done'?{result:job.result}:{}),...(job.status==='failed'?{error:job.error_code||'answer_failed'}:{})});
 const run=async(job:AnswerJob)=>{
  try{
   if(!await d.authorize(job)){await d.store.finish(job.id,null,'authorization_changed');return;}
   const remaining=Date.parse(job.deadline_at)-now()-15000;
   if(remaining<=0){await d.store.finish(job.id,null,'answer_timeout');return;}
   const result=await d.execute(job,timeout(remaining));
   if(now()>=Date.parse(job.deadline_at)){await d.store.finish(job.id,null,'answer_timeout');return;}
   await d.store.finish(job.id,result);
  }catch(error){
   const name=(error as Error)?.name,code=(error as {code?:string})?.code;
   const safe=code==='semantic_disabled'?'semantic_disabled':['TimeoutError','AbortError'].includes(name)?'answer_timeout':'answer_failed';
   try{await d.store.finish(job.id,null,safe);}catch{/* Persistent deadline bounds an interrupted worker, too. */}
  }
 };
 return {
  async start(actor:AnswerActor,chatId:string,input:Record<string,unknown>){
   const requestId=String(input.request_id||''),query=typeof input.query==='string'?input.query.trim():'',mode=String(input.mode||'');
   if(!uuid.test(requestId)||!query||query.length>4000||!['normal','semantic','fast'].includes(mode))throw new AnswerJobError('invalid_answer_request');
   const inputHash=await hash(JSON.stringify([chatId,mode,query]));
   const admitted=await d.store.admit({user_id:actor.id,chat_id:chatId,request_id:requestId,request_hash:inputHash,auth_version:actor.authVersion,parent_session_ref:actor.sessionRef,mode:mode as AnswerMode,query,deadline_at:new Date(now()+ANSWER_BUDGET_MS).toISOString()});
   if(admitted.conflict)throw new AnswerJobError('answer_request_conflict',409);
   if(admitted.busy)throw new AnswerJobError('answer_in_progress',409);
   if(!admitted.job)throw new AnswerJobError('answer_unavailable',503);
   if(admitted.job.auth_version!==actor.authVersion)throw new AnswerJobError('answer_not_found',404);
   if(admitted.created)d.schedule(run(admitted.job));
   return visible(admitted.job);
  },
  async get(actor:AnswerActor,chatId:string,id:string){
   if(!uuid.test(id))throw new AnswerJobError('answer_not_found',404);
   const job=await d.store.get(id,actor.id,chatId);
   if(!job||job.auth_version!==actor.authVersion)throw new AnswerJobError('answer_not_found',404);
   if(job.status==='running'&&Date.parse(job.deadline_at)<=now()){
    await d.store.finish(id,null,'answer_timeout');job.status='failed';job.error_code='answer_timeout';
   }
   return visible(job);
  }
 };
}

export function createRestAnswerStore(rest:(path:string,options?:RequestInit)=>Promise<any>):AnswerJobStore{
 return {
  admit:async(input)=>rest('rpc/qa_admit_answer_job',{method:'POST',body:JSON.stringify({job:input})}),
  get:async(id,userId,chatId)=>{
   const q=new URLSearchParams({id:'eq.'+id,user_id:'eq.'+userId,chat_id:'eq.'+chatId,select:'*',limit:'1'});
   return (await rest('qa_answer_jobs?'+q))[0]||null;
  },
  finish:async(id,result,error)=>{
   await rest('qa_answer_jobs?id=eq.'+encodeURIComponent(id)+'&status=eq.running',{method:'PATCH',headers:{Prefer:'return=minimal'},body:JSON.stringify({status:error?'failed':'done',result:error?null:result,error_code:error||null,finished_at:new Date().toISOString()})});
  }
 };
}

export function compactAnswerResult(value:any){
 const project=(row:any,keys:string[])=>Object.fromEntries(keys.filter(k=>row&&row[k]!==undefined).map(k=>[k,k==='content'?String(row[k]||'').slice(0,800):row[k]]));
 const clip=(rows:any,keys:string[])=>{if(typeof rows==='string'){try{rows=JSON.parse(rows);}catch{rows=[];}}return Array.isArray(rows)?rows.slice(0,200).map(r=>project(r,keys)):[];};
 const commentKeys=['comment_id','source_type','posted_at','author_name','content','forum_category','topic_title','source_system','source_kind','lesson_title','lesson_url','course_tab','citation_label'];
 const chunkKeys=['chunk_key','source_id','source_key','start_sec','end_sec','content','citation_label'];
 const sourceKeys=['id','source_key','title','video_url','content_channel'];
 const lineKeys=['id','route_id','chat_title','chat_name','stream_type','thread_title','posted_at','post_date','sender_name','content','citation_label'];
 const used=value?.usedSources||value?.used_sources||'';
 return {...(['normal-v2','normal-legacy','normal-legacy-fallback','fast-legacy'].includes(value?.pipeline)?{pipeline:value.pipeline}:{}),answer:String(value?.answer||''),usedSources:typeof used==='string'?used:JSON.stringify(used),relatedComments:clip(value?.relatedComments,commentKeys),relatedLessonComments:clip(value?.relatedLessonComments,commentKeys),relatedChunks:clip(value?.relatedChunks,chunkKeys),relatedSources:clip(value?.relatedSources,sourceKeys),relatedOpenchat:clip(value?.relatedOpenchat,lineKeys),referenceLabels:value?.referenceLabels||{},referenceSelection:['mentioned','provided-context'].includes(value?.referenceSelection)?value.referenceSelection:'unknown'};
}
