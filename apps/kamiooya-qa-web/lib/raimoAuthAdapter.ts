import {createAnswerJobs,createRestAnswerStore,compactAnswerResult} from './qaAnswerJobs.ts';
// Runtime-neutral production adapters. Secrets are injected only by the Edge entrypoint.
import type { GatewayDependencies } from './raimoAuthGateway.ts';
export type RuntimeConfig = { origin: string; raimoBase: string; gatewaySecret: string; projectUrl: string; serviceKey: string; proxySecret: string };
export const digest = async (s: string) => Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256', new TextEncoder().encode(s))), b => b.toString(16).padStart(2, '0')).join('');
export class UpstreamError extends Error {
  code: string; status: number;
  constructor(code: string, status: number) { super(code); this.code=code; this.status=status; }
}
export function createProductionAdapter(c: RuntimeConfig, verify: (raw: string, stored: string) => Promise<boolean>, hash: (raw: string) => Promise<string>, transport: typeof fetch = fetch, jobsRuntime?:{schedule(task:Promise<void>):void;semantic(req:Request):Promise<Response>}) {
  if (!/^https:\/\//.test(c.raimoBase) || !c.raimoBase.startsWith(c.origin+'/miniAppApi/') ||
      !/^https:\/\/[a-z]+\.supabase\.co$/.test(c.projectUrl) || [c.gatewaySecret,c.proxySecret].some(v=>v.length<32) || !c.serviceKey) throw new Error('invalid_configuration');
  const auth = { apikey:c.serviceKey, Authorization:'Bearer '+c.serviceKey, 'Content-Type':'application/json' };
  const rest = async (path: string, options: RequestInit={}) => {
    const r=await transport(c.projectUrl+'/rest/v1/'+path,{...options,headers:{...auth,...options.headers},signal:AbortSignal.timeout(20000)});
    if(!r.ok) throw new Error('persistence_unavailable');
    const text=await r.text();
    return text?JSON.parse(text):null;
  };
  const backend = async (method: string, path: string, input: Record<string,unknown>={}, signal?:AbortSignal) => {
    // Read aliases keep the server proof in a POST body, never in URLs or access logs.
    // The server proof is never supplied by the browser.
    let url=c.raimoBase+(method==='GET'?'/internal/read':'')+path;
    const data={...input,__gateway_secret:c.gatewaySecret};
    const options:RequestInit={method:method==='GET'?'POST':method,headers:{'Content-Type':'application/json'},signal:signal||AbortSignal.timeout(60000),redirect:'error'};
    options.body=JSON.stringify(data);
    const r=await transport(url,options);
    let result;try{result=await r.json();}catch{throw new Error('backend_unavailable');}
    if(!r.ok) {
      const codes=['email_taken','not_on_roster','already_registered','invalid_token','not_approved','user_not_found','forbidden','member_not_found'];
      const code=codes.includes(result.errorCode)?result.errorCode:'operation_failed';
      throw new UpstreamError(code,r.status>=500?503:400);
    }
    return result;
  };
  const lookup = async (input: Record<string,unknown>) => { const field=Object.keys(input)[0];if(!['email','user_id','reset_token'].includes(field))throw new Error('invalid_lookup');return (await backend('POST','/internal/auth-user/'+field,input)).user || null; };
  const memberOf = async (u:any) => u ? { id:String(u.id),email:String(u.email),role:String(u.role),status:String(u.status),authVersion:await digest(c.gatewaySecret+'\u0000'+String(u.password_hash||'')),name:u.name,member_no:u.member_no,prefecture:u.prefecture } : null;
  const sessions:GatewayDependencies['sessions']={
    async get(token){ const rows=await rest('raimo_auth_sessions?token_hash=eq.'+await digest(token)+'&select=user_id,auth_version,expires_at&limit=1'); const r=rows[0];return r?{uid:r.user_id,authVersion:r.auth_version,expires:Date.parse(r.expires_at)}:null; },
    async put(token,s){await rest('raimo_auth_sessions',{method:'POST',headers:{Prefer:'return=minimal'},body:JSON.stringify({token_hash:await digest(token),user_id:s.uid,auth_version:s.authVersion,expires_at:new Date(s.expires).toISOString()})});},
    async delete(token){await rest('raimo_auth_sessions?token_hash=eq.'+await digest(token),{method:'DELETE',headers:{Prefer:'return=minimal'}});}
  };
  const allow = async (key:string,max=10) => await rest('rpc/raimo_auth_take_limit',{method:'POST',body:JSON.stringify({key_hash:await digest(key),max_attempts:max,window_seconds:900})})===true;
  const status = async (uid:string,ref:string) => {
    if(!/^[0-9a-f]{64}$/.test(ref)) return {user_id:uid,session_active:false};
    const rows=await rest('raimo_auth_sessions?token_hash=eq.'+ref+'&select=user_id,auth_version,expires_at&limit=1');
    const s=rows[0],u=await memberOf(await lookup({user_id:uid}));
    return {user_id:uid,status:u?.status,role:u?.role,session_active:!!(s&&s.user_id===uid&&Date.parse(s.expires_at)>Date.now()&&s.auth_version===u?.authVersion)};
  };
  const deps:GatewayDependencies={origin:c.origin,sessions,allowLogin:email=>allow('login:'+email),
    authenticate:async(email,password)=>{const u=await lookup({email});if(!u||!await verify(password,String(u.password_hash||'')))return null;return memberOf(u);},
    member:async id=>memberOf(await lookup({user_id:id})),
    chatOwner:async id=>{const r=await backend('GET','/chat-sessions/'+id);return r.session?String(r.session.user_id):null;},
    forward:async(method,path,input)=>{
      if(['/admin/master-transfer/validate','/admin/master-transfer/accept'].includes(path)){
        const x=await backend('POST','/admin/master-transfer/validate',{token:input.token});
        if(!(Date.parse(x.expires_at)>Date.now()) || String(x.to_user_id)!==String(input.actor_user_id))throw new UpstreamError('invalid_token',400);
        if(path.endsWith('/accept'))input={...input,from_user_id:x.from_user_id};
      }
      if(path==='/admin/master-transfer/start')input={...input,expires_at:new Date(Date.now()+86400000).toISOString()};
      if(path.startsWith('/admin/comments')){
        const isPrivate=(r:any)=>r && (String(r.comment_id||'').startsWith('admin_') || ['__admin_meta__','__master_xfer__'].includes(String(r.source_type)));
        if(isPrivate(input))throw new UpstreamError('forbidden',403);
        if(input.comment_id || /\/delete$/.test(path)){
          const field=input.comment_id?'comment_id':'id',value=input.comment_id||path.split('/')[3];
          const r=await backend('POST','/internal/auth-comment/'+field,{[field]:value});
          if(isPrivate(r.comment))throw new UpstreamError('forbidden',403);
        }
      }
      return backend(method,path,input);
    },
    attachmentSession:async(uid,parent)=>{
      const r=await transport(c.projectUrl+'/functions/v1/community-attachments',{method:'POST',headers:{'Content-Type':'application/json',Authorization:'Bearer '+c.proxySecret},body:JSON.stringify({operation:'session',user_id:uid,parent_session:parent}),signal:AbortSignal.timeout(20000)});
      if(!r.ok)throw new Error('attachments_unavailable');return r.json();
    },
    referenceEvents:async(userId,chatId)=>{
      // The inspected legacy deployment used context order for these recent semantic events.
      // Bound recovery to the archived pre-stable-label deployment. New filtered IDs
      // are not positional labels; those answers recover their persisted job DTO instead.
      const q=new URLSearchParams({select:'created_at,query_text,used_sources',user_id:'eq.'+userId,session_id:'eq.'+chatId,search_mode:'eq.semantic',result_status:'eq.ok',and:'(created_at.gte.2026-11-04T00:00:00+09:00,created_at.lt.2026-11-06T06:53:00+09:00)',order:'created_at.desc',limit:'100'});
      const events=await rest('app_qa_search_events?'+q),keys=new Set<string>();
      for(const event of events){try{const ids=typeof event.used_sources==='string'?JSON.parse(event.used_sources):event.used_sources;for(const key of ids?.chunk_keys||[])if(typeof key==='string'&&/^[a-zA-Z0-9:_|.\/-]{1,250}$/.test(key))keys.add(key);}catch{}}
      const chunks:any[]=[];const selected=[...keys].slice(0,500);
      for(let offset=0;offset<selected.length;offset+=20){
        const query=new URLSearchParams({select:'chunk_key,source_id,source_key,start_sec,end_sec,content',chunk_key:'in.('+selected.slice(offset,offset+20).join(',')+')',limit:'20'});
        const rows=await rest('knowledge_chunks?'+query);chunks.push(...rows.map((r:any)=>({...r,content:String(r.content||'').slice(0,800)})));
      }
      const sources=await rest('knowledge_sources?select=id,source_key,title,video_url&limit=1000');
      const jq=new URLSearchParams({select:'finished_at,query,result',user_id:'eq.'+userId,chat_id:'eq.'+chatId,status:'eq.done',order:'finished_at.desc',limit:'20'});
      const jobs=await rest('qa_answer_jobs?'+jq);
      return {events,chunks,sources,jobs};
    },
    referenceMetadata:async()=>rest('rpc/qa_reference_metadata',{method:'POST',body:'{}'}),
    semanticConfig:async()=>{
      const r=await backend('POST','/semantic-search-config',{});
      if(r?.url!==c.projectUrl+'/functions/v1/semantic-search' || typeof r.secret!=='string' ||
        r.secret.length<32 || r.secret.length>256 || [c.gatewaySecret,c.proxySecret,c.serviceKey].includes(r.secret))throw new Error('invalid_semantic_configuration');
      // Explicit projection: only the existing client-side search credential, never backend extras.
      return {url:r.url,secret:r.secret};
    },
    publicAction:async(path,input)=>{
      const email=String(input.email||'').trim().toLowerCase();
      if(!await allow('public:'+path+':'+(email||String(input.token||'')),5))throw new UpstreamError('try_later',429);
      if(['/auth/register','/auth/reregister','/auth/register-roster','/auth/reregister-roster'].includes(path)){
        const password=String(input.password_hash||'');if(password.length<8||new TextEncoder().encode(password).length>72)throw new UpstreamError('invalid_password',400);
        const data={email,password_hash:await hash(password),name:String(input.name||'').slice(0,200),member_no:String(input.member_no||'').slice(0,100),prefecture:String(input.prefecture||'').slice(0,50)};
        const r=await backend('POST',path,data);
        if(!path.endsWith('-roster'))await backend('POST','/notify/registration',{email,member_no:data.member_no,note:'アプリ登録',registered_at:new Date().toISOString()});
        return r;
      }
      if(path==='/auth/reset-password/check')return {email}; // no unauthenticated account enumeration
      if(path==='/auth/forgot-password/issue'){
        const u=await lookup({email});
        if(u?.status==='approved'){
          const token=crypto.randomUUID()+crypto.randomUUID();const expires_at=new Date(Date.now()+1800000).toISOString();
          await backend('POST',path,{email,token:await digest(token),expires_at});
          await backend('POST','/notify/password-reset',{email,expires_at,reset_url:c.origin+'/#reset-password?token='+encodeURIComponent(token)});
        }
        return {success:true};
      }
      if(['/auth/forgot-password/validate','/auth/reset-password'].includes(path)){
        const token=String(input.token||'');if(token.length<32||token.length>200)throw new UpstreamError('invalid_token',400);
        const u=await lookup({reset_token:await digest(token)});
        if(!u||u.status!=='approved'||!(Date.parse(u.reset_expires_at)>Date.now()))throw new UpstreamError('invalid_token',400);
        if(path.endsWith('/validate'))return {email:u.email,token,expires_at:u.reset_expires_at};
        const password=String(input.password_hash||'');if(password.length<8||new TextEncoder().encode(password).length>72)throw new UpstreamError('invalid_password',400);
        return backend('POST',path,{token:await digest(token),password_hash:await hash(password)});
      }
      // Legacy browser notifications are redundant: issuance above performs the operation server-side.
      if(['/notify/password-reset','/notify/registration'].includes(path))return {ok:true};
      throw new UpstreamError('route_not_reviewed',403);
    }
  };
  if(jobsRuntime)deps.jobs=createAnswerJobs({
    store:createRestAnswerStore(rest),schedule:jobsRuntime.schedule,
    authorize:async job=>{
      const u=await deps.member(job.user_id),s=await status(job.user_id,job.parent_session_ref);
      return !!(u&&u.status==='approved'&&u.authVersion===job.auth_version&&s.session_active&&await deps.chatOwner(job.chat_id)===job.user_id);
    },
    execute:async(job,signal)=>{
      if(job.mode!=='semantic'){
        const result=compactAnswerResult(await backend('POST','/chat-sessions/'+job.chat_id+(job.mode==='fast'?'/messages-fast':'/messages'),{content:job.query,actor_user_id:job.user_id},signal));
        if(!result.answer.trim())throw new Error('empty_answer');return result;
      }
      const cfg=await deps.semanticConfig!();
      await backend('POST','/chat-sessions/'+job.chat_id+'/messages-append',{role:'user',content:job.query},signal);
      const response=await jobsRuntime.semantic(new Request(cfg.url,{method:'POST',headers:{'Content-Type':'application/json','X-Semantic-Shared-Secret':cfg.secret},body:JSON.stringify({query:job.query,session_id:job.chat_id,user_id:job.user_id,comment_limit:100,chunk_limit:50,openchat_limit:20,match_threshold:0.22}),signal}));
      const result=await response.json();
      if(!response.ok){if(signal.aborted)throw signal.reason;throw new UpstreamError(result?.code==='semantic_disabled'?'semantic_disabled':'operation_failed',503);}
      const answer=String(result.answer||'').trim();if(!answer)throw new Error('empty_answer');
      await backend('POST','/chat-sessions/'+job.chat_id+'/messages-append',{role:'assistant',content:answer},signal);
      return compactAnswerResult(result);
    }
  });
  return {deps, status, allow, backend};
}
