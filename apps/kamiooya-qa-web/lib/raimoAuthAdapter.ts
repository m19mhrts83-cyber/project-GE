import {createAnswerJobs,createRestAnswerStore,compactAnswerResult} from './qaAnswerJobs.ts';
import {featureAllowed} from './featureFlags.ts';
import {matchPending} from './rosterMatch.ts';
import {answerTier,cacheable,queryKey,fresh} from './answerCost.ts';
import {answerHash,cleanMeta,RAIMO_ANSWER_MODEL,type AnswerMeta} from './answerMeta.ts';
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
  const parentSession=async(ref:string)=>{
    if(!/^[0-9a-f]{64}$/.test(ref))return null;
    return (await rest('raimo_auth_sessions?token_hash=eq.'+ref+'&select=user_id,auth_version,expires_at&limit=1'))[0]||null;
  };
  const sessionActive=(uid:string,s:any,u:any)=>!!(s&&s.user_id===uid&&Date.parse(s.expires_at)>Date.now()&&s.auth_version===u?.authVersion);
  const status = async (uid:string,ref:string) => {
    if(!/^[0-9a-f]{64}$/.test(ref))return {user_id:uid,session_active:false};
    const [s,u]=await Promise.all([parentSession(ref),lookup({user_id:uid}).then(memberOf)]);
    return {user_id:uid,status:u?.status,role:u?.role,session_active:sessionActive(uid,s,u)};
  };

  const rosterHas=async(hashes:string[])=>{
    const found=new Set<string>();const list=hashes.filter(h=>/^[0-9a-f]{64}$/.test(h));
    for(let i=0;i<list.length;i+=100){const rows=await rest('qa_roster_hashes?select=hash&hash=in.('+list.slice(i,i+100).join(',')+')');for(const r of rows||[])found.add(String(r.hash));}
    return found;
  };
  // スイッチ auto_approval が「全員」なら全員に、owner/reviewers なら名指しのメールの人の登録だけに効く（試験用）。
  const autoApprove=async(email:string,memberNo:string,name:string)=>{
    const flags=await rest('qa_feature_flags?select=feature,stage,owner_ids,reviewer_ids&feature=eq.auto_approval&limit=1');
    if(!featureAllowed(Array.isArray(flags)?flags[0]:undefined,{id:'',email}))return false;
    const u=await lookup({email});
    if(!u||u.status!=='pending')return false;
    const pending=await backend('GET','/admin/users/pending',{});
    // 本人は今回の登録内容で照合し、ほかの承認待ちは同じ番号がいないかを見るのに使う
    const users=(Array.isArray(pending?.users)?pending.users:[]).filter((x:any)=>String(x.id)!==String(u.id)).map((x:any)=>({id:String(x.id),member_no:x.member_no,name:x.name}));
    users.push({id:String(u.id),member_no:memberNo,name});
    const result=(await matchPending(users,rosterHas))[String(u.id)];
    if(result!=='match')return false;
    await backend('PUT','/admin/users/'+encodeURIComponent(String(u.id))+'/approve',{});
    await backend('POST','/notify/approval',{email}).catch(()=>{}); // メールが失敗しても承認は済んでいる（ログインはできる）
    return true;
  };

  const deps:GatewayDependencies={origin:c.origin,sessions,allowLogin:email=>allow('login:'+email),
    authenticate:async(email,password)=>{const u=await lookup({email});if(!u||!await verify(password,String(u.password_hash||'')))return null;return memberOf(u);},
    member:async id=>memberOf(await lookup({user_id:id})),
    chatOwner:async id=>{const r=await backend('GET','/chat-sessions/'+id);return r.session?String(r.session.user_id):null;},
    forward:async(method,path,input)=>{
      if(method==='POST'&&path==='/comments-page'){
        const after=Number(input.after_id??0);
        if(!Number.isSafeInteger(after)||after<0)throw new UpstreamError('invalid_request',400);
        const result=await backend('POST','/internal/read/comments-page',{after_id:after});
        if(!Array.isArray(result.comments)||result.comments.length>500)throw new Error('invalid_comment_page');
        const keys=['id','source_type','comment_id','posted_at','author_name','content','parent_comment_id','created_at','updated_at','source_system','source_kind','forum_category','topic_title','course_tab','section_name','lesson_title','lesson_url','content_hash'];
        return {comments:result.comments.map((row:any)=>Object.fromEntries(keys.filter(k=>row[k]!==undefined).map(k=>[k,row[k]])))};
      }
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
      const jq=new URLSearchParams({select:'finished_at,query,result',user_id:'eq.'+userId,chat_id:'eq.'+chatId,status:'eq.done',order:'finished_at.desc',limit:'20'});
      const [events,sources,jobs]=await Promise.all([rest('app_qa_search_events?'+q),rest('knowledge_sources?select=id,source_key,title,video_url&limit=1000'),rest('qa_answer_jobs?'+jq)]);
      const keys=new Set<string>();
      for(const event of events){try{const ids=typeof event.used_sources==='string'?JSON.parse(event.used_sources):event.used_sources;for(const key of ids?.chunk_keys||[])if(typeof key==='string'&&/^[a-zA-Z0-9:_|.\/-]{1,250}$/.test(key))keys.add(key);}catch{}}
      const chunks:any[]=[];const selected=[...keys].slice(0,500);
      for(let offset=0;offset<selected.length;offset+=80){
        const group=[];
        for(let start=offset;start<Math.min(offset+80,selected.length);start+=20){
          const query=new URLSearchParams({select:'chunk_key,source_id,source_key,start_sec,end_sec,content',chunk_key:'in.('+selected.slice(start,start+20).join(',')+')',limit:'20'});
          group.push(rest('knowledge_chunks?'+query));
        }
        const pages=await Promise.all(group);
        chunks.push(...pages.flat().map((r:any)=>({...r,content:String(r.content||'').slice(0,800)})));
      }
      return {events,chunks,sources,jobs};
    },
    referenceMetadata:async()=>rest('rpc/qa_reference_metadata',{method:'POST',body:'{}'}),
    featureFlags:async()=>rest('qa_feature_flags?select=feature,stage,owner_ids,reviewer_ids&limit=100'),
    roster:{
      has:rosterHas,
      meta:async()=>{const m=(await rest('qa_roster_meta?select=row_count,synced_at&id=eq.1&limit=1'))?.[0];return {row_count:m?.row_count,synced_at:m?.synced_at};}
    },
    listFeedback:async()=>rest('qa_answer_feedback?select=chat_id,message_id,rating,reasons,comment,question,answer,updated_at,answer_mode,answer_tier,answer_model,answer_reused&order=updated_at.desc&limit=200'),
    saveSourceClick:async row=>{await rest('qa_answer_source_clicks?on_conflict=user_id,chat_id,message_id,kind,source_key',{method:'POST',headers:{Prefer:'resolution=merge-duplicates,return=minimal'},body:JSON.stringify(row)});},
    listSourceClicks:async()=>rest('qa_answer_source_clicks?select=user_id,chat_id,message_id,kind,source_key,title,label&order=clicked_at.desc&limit=1000'),
    // (2) 答えの作り方（モデル・使い回し）。評価のときに本文のハッシュで引く。11/11
    answerMeta:async(userId,chatId,answer)=>{
      const h=await answerHash(answer);
      const row=(await rest('qa_answer_meta?user_id=eq.'+encodeURIComponent(userId)+'&chat_id=eq.'+encodeURIComponent(chatId)+'&answer_hash=eq.'+h+'&select=mode,tier,model,reused&limit=1'))[0];
      return cleanMeta(row);
    },
    listChangeLog:async()=>rest('qa_change_log?visible=is.true&select=released_on,title,body,trigger&order=released_on.desc,id.desc&limit=200'),
    saveFeedback:async row=>{await rest('qa_answer_feedback?on_conflict=user_id,chat_id,message_id',{method:'POST',headers:{Prefer:'resolution=merge-duplicates,return=minimal'},body:JSON.stringify(row)});},
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
        if(path.endsWith('-roster'))return r;
        // (3) 名簿（目標設定・合格状況）と会員番号＋氏名が合えば、その場で承認して本人に完了メール（11/10 松野さん）。
        // 合わない・同じ番号の承認待ちがいる・照合できないときは、今までどおり承認待ち。
        const auto=await autoApprove(email,data.member_no,data.name).catch(()=>false);
        await backend('POST','/notify/registration',{email,member_no:data.member_no,note:auto?'アプリ登録（名簿一致で自動承認済み・対応不要）':'アプリ登録',registered_at:new Date().toISOString()});
        return auto?{...r,auto_approved:'true'}:r;
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
  const recordMeta=(job:{user_id:string;chat_id:string},answer:string,m:AnswerMeta)=>answerHash(answer)
    .then(h=>rest('qa_answer_meta?on_conflict=user_id,chat_id,answer_hash',{method:'POST',headers:{Prefer:'resolution=merge-duplicates,return=minimal'},
      body:JSON.stringify({user_id:job.user_id,chat_id:job.chat_id,answer_hash:h,...m,created_at:new Date().toISOString()})}))
    .catch(()=>{/* 記録できなくても答えは返す */});
  if(jobsRuntime)deps.jobs=createAnswerJobs({
    store:createRestAnswerStore(rest),schedule:jobsRuntime.schedule,
    authorize:async job=>{
      const [u,parent,owner]=await Promise.all([deps.member(job.user_id),parentSession(job.parent_session_ref),deps.chatOwner(job.chat_id)]);
      return !!(u&&u.status==='approved'&&u.authVersion===job.auth_version&&sessionActive(job.user_id,parent,u)&&owner===job.user_id);
    },
    execute:async(job,signal)=>{
      // deep = (1)の「より詳しく調べる」。意味検索を上位のモデルで、使い回しなしで答える。
      if(job.mode!=='semantic'&&job.mode!=='deep'){
        const result=compactAnswerResult(await backend('POST','/chat-sessions/'+job.chat_id+(job.mode==='fast'?'/messages-fast':'/messages'),{content:job.query,actor_user_id:job.user_id},signal));
        if(!result.answer.trim())throw new Error('empty_answer');
        await recordMeta(job,result.answer,{mode:job.mode==='fast'?'fast':'normal',tier:'standard',model:RAIMO_ANSWER_MODEL,reused:false});
        return result;
      }
      const cfg=await deps.semanticConfig!();
      await backend('POST','/chat-sessions/'+job.chat_id+'/messages-append',{role:'user',content:job.query},signal);
      // (1) 使用量の削減。スイッチ cost_saving が見える人の質問だけ。読めなければ今までどおり。
      let saving=false,withContext=false;
      try{
        const flags=await deps.featureFlags!();const list=Array.isArray(flags)?flags:[];
        // オフ・全員公開のときは本人を引き直さない（会員情報の読み出しを増やさない）
        let me:{id:string;email:string}|null|undefined;
        const allowed=async(name:string)=>{
          const flag=list.find((f:any)=>f.feature===name);
          if(!flag||!['owner','reviewers','all'].includes(flag.stage))return false;
          if(flag.stage==='all')return true;
          if(me===undefined){const u=await deps.member(job.user_id);me=u?{id:u.id,email:u.email}:null;}
          return !!me&&featureAllowed(flag,me);
        };
        saving=await allowed('cost_saving');
        // 同じチャットの直前のやり取りを踏まえて探す・答える（スイッチ chat_context、2026-11-11）。
        withContext=await allowed('chat_context');
      }catch{saving=false;withContext=false;}
      let history:{question:string;answer:string}[]=[];
      if(withContext){
        try{
          const hq=new URLSearchParams({select:'query,result,created_at',user_id:'eq.'+job.user_id,chat_id:'eq.'+job.chat_id,status:'eq.done',id:'neq.'+job.id,order:'created_at.desc',limit:'2'});
          const rows=await rest('qa_answer_jobs?'+hq);
          history=(Array.isArray(rows)?rows:[]).reverse().map((r:any)=>({question:String(r?.query||'').slice(0,500),answer:String(r?.result?.answer||'').slice(0,1500)})).filter(t=>t.question);
        }catch{history=[];/* 読めなければ今までどおり（その質問だけで探す） */}
      }
      const deep=job.mode==='deep';
      // 前のやり取りを踏まえた答えは、同じ文面の質問でも中身が変わるので使い回さない・保存しない。
      const reuse=saving&&!deep&&!history.length;
      const key=reuse?await queryKey(job.query):'';
      if(reuse){
        try{
          const row=(await rest('qa_answer_cache?query_hash=eq.'+key+'&select=result,created_at,hits,tier&limit=1'))[0];
          if(row&&fresh(row)&&cacheable(String(row.result?.answer||''))){
            const reused=compactAnswerResult(row.result);
            await backend('POST','/chat-sessions/'+job.chat_id+'/messages-append',{role:'assistant',content:reused.answer},signal);
            rest('qa_answer_cache?query_hash=eq.'+key,{method:'PATCH',headers:{Prefer:'return=minimal'},body:JSON.stringify({hits:Number(row.hits||0)+1,last_hit_at:new Date().toISOString()})}).catch(()=>{});
            await recordMeta(job,reused.answer,{mode:'semantic',tier:row.tier==='lite'?'lite':'standard',model:String(row.result?.answerModel||''),reused:true});
            return {...reused,reused:true};
          }
        }catch{/* 使い回しが読めなくても答えは作る */}
      }
      const tier=saving&&!deep?answerTier(job.query):'standard';
      const response=await jobsRuntime.semantic(new Request(cfg.url,{method:'POST',headers:{'Content-Type':'application/json','X-Semantic-Shared-Secret':cfg.secret},body:JSON.stringify({query:job.query,session_id:job.chat_id,user_id:job.user_id,comment_limit:100,chunk_limit:50,openchat_limit:20,match_threshold:0.22,...(tier==='lite'?{answer_tier:'lite'}:{}),...(history.length?{history}:{})}),signal}));
      const result=await response.json();
      if(!response.ok){if(signal.aborted)throw signal.reason;throw new UpstreamError(result?.code==='semantic_disabled'?'semantic_disabled':'operation_failed',503);}
      const answer=String(result.answer||'').trim();if(!answer)throw new Error('empty_answer');
      await backend('POST','/chat-sessions/'+job.chat_id+'/messages-append',{role:'assistant',content:answer},signal);
      const compact=compactAnswerResult(result);
      // 実際に答えたモデル（軽いモデルが使えず今のモデルに戻った場合もそちら）。古い意味検索は返さないので空＝不明。
      const answerModel=typeof result.answerModel==='string'?result.answerModel:'';
      await recordMeta(job,answer,{mode:deep?'deep':'semantic',tier,model:answerModel,reused:false});
      if(reuse&&cacheable(answer)){
        await rest('qa_answer_cache?on_conflict=query_hash',{method:'POST',headers:{Prefer:'resolution=merge-duplicates,return=minimal'},body:JSON.stringify({query_hash:key,query:job.query.slice(0,4000),result:{...compact,answerModel},tier,hits:0,created_at:new Date().toISOString(),last_hit_at:null})}).catch(()=>{});
      }
      return compact;
    }
  });
  return {deps, status, allow, backend};
}
