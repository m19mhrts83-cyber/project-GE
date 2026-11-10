import type {AnswerActor} from './qaAnswerJobs.ts';
import {featuresFor, requireFeature, type FeatureFlag} from './featureFlags.ts';
import {parseFeedback, feedbackRow} from './answerFeedback.ts';
// Shared gateway: the production adapter supplies persistent sessions and live membership checks.
type Member = { id: string; email: string; role: string; status: string; authVersion: string; name?: string; member_no?: string; prefecture?: string };
type Session = { uid: string; authVersion: string; expires: number };
export type GatewayDependencies = {
  origin: string;
  authenticate(email: string, password: string): Promise<Member | null>;
  member(id: string): Promise<Member | null>;
  sessions: { get(token: string): Promise<Session | null>; put(token: string, value: Session): Promise<void>; delete(token: string): Promise<void> };
  allowLogin(email: string): Promise<boolean>;
  chatOwner(id: string): Promise<string | null>;
  forward(method: string, path: string, input: Record<string, unknown>): Promise<unknown>;
  attachmentSession(uid: string, parentSession: string): Promise<unknown>;
  jobs?: {start(actor:AnswerActor,chatId:string,input:Record<string,unknown>):Promise<unknown>;get(actor:AnswerActor,chatId:string,id:string):Promise<unknown>};
  referenceEvents?(userId:string,chatId:string):Promise<unknown>;
  referenceMetadata?(): Promise<unknown>;
  semanticConfig?(): Promise<{url: string; secret: string}>;
  publicAction?(path: string, input: Record<string, unknown>): Promise<unknown>;
  // 段階公開スイッチ（lib/featureFlags.ts）。未設定なら全機能オフ。
  featureFlags?(): Promise<FeatureFlag[]>;
  saveFeedback?(row: Record<string, unknown>): Promise<void>;
  listFeedback?(): Promise<unknown[]>;
  now?: () => number;
};
const approved = (u: Member | null): u is Member => !!u && u.status === 'approved' && ['user', 'admin', 'master_admin'].includes(u.role) && !!u.authVersion;
const publicUser = (u: Member) => ({ id: u.id, email: u.email, role: u.role, status: u.status, ...(u.name !== undefined ? {name:u.name}:{}), ...(u.member_no !== undefined ? {member_no:u.member_no}:{}), ...(u.prefecture !== undefined ? {prefecture:u.prefecture}:{}) });
// Only explicitly reviewed operations may pass; all other legacy routes stay closed.
function permission(method: string, path: string): 'member' | 'staff' | 'master' | 'chat' | 'own-list' | null {
  if (method === 'POST' && path === '/comments-page') return 'member';
  if (method === 'GET' && ['/comments', '/knowledge-chunks', '/knowledge-sources', '/suggested-questions'].includes(path)) return 'member';
  if (method === 'GET' && ['/admin/users', '/admin/users/pending'].includes(path)) return 'staff';
  if (method === 'PUT' && /^\/admin\/users\/[a-zA-Z0-9_-]+\/(approve|reject)$/.test(path)) return 'master';
  if (method === 'POST' && path === '/chat-sessions') return 'member';
  if ((method === 'POST' && path === '/suggested-questions') || (method === 'PUT' && /^\/suggested-questions\/[a-zA-Z0-9_-]+\/increment$/.test(path))) return 'member';
  if ((method === 'GET' && ['/admin/members','/admin/role-requests/pending'].includes(path)) ||
      (method === 'POST' && /^\/admin\/(members(?:\/update)?|comments(?:\/update-(category|content|posted-at)|\/[a-zA-Z0-9_-]+\/delete)?|knowledge-sources(?:\/update)?|knowledge-chunks(?:\/delete-by-source)?|users\/[a-zA-Z0-9_-]+\/role-requests)$/.test(path))) return 'staff';
  if(method==='GET' && path==='/admin/master-transfer/pending')return 'master';
  if ((method === 'POST' && /^\/admin\/users\/[a-zA-Z0-9_-]+\/set-role$/.test(path)) ||
      (method === 'PUT' && /^\/admin\/(users\/[a-zA-Z0-9_-]+\/withdraw|role-requests\/[a-zA-Z0-9_-]+\/(approve|reject))$/.test(path)) ||
      (method === 'POST' && ['/admin/master-transfer/start','/admin/master-transfer/cancel'].includes(path))) return 'master';
  if (method === 'POST' && ['/admin/master-transfer/validate','/admin/master-transfer/accept'].includes(path)) return 'staff';
  if (method === 'POST' && ['/notify/approval','/notify/rejection','/notify/master-transfer'].includes(path)) return 'master';
  if (method === 'GET' && /^\/users\/[a-zA-Z0-9_-]+\/chat-sessions$/.test(path)) return 'own-list';
  if ((method === 'GET' && /^\/chat-sessions\/[a-zA-Z0-9_-]+$/.test(path)) ||
      (method === 'PUT' && /^\/chat-sessions\/[a-zA-Z0-9_-]+\/touch$/.test(path)) ||
      (method === 'POST' && /^\/chat-sessions\/[a-zA-Z0-9_-]+\/messages(?:-append|-fast|-semantic|-semantic-fast)?$/.test(path))) return 'chat';
  return null;
}
// Deny-by-default user projection rather than recursive deletion of a few field names.
function safeUsers(result: unknown): unknown {
  const safe = (u: any) => publicUser(u);
  const r = result as any;
  if (!r || !Array.isArray(r.users)) throw new Error('invalid_users_response');
  return { users: r.users.map(safe) };
}
function stripPrivate(value: unknown): unknown {
  if(Array.isArray(value))return value.map(stripPrivate);
  if(value && typeof value==='object')return Object.fromEntries(Object.entries(value).filter(([k])=>!['password','password_hash','reset_token','reset_expires_at','authVersion','auth_version','secret','__gateway_secret'].includes(k)).map(([k,v])=>[k,stripPrivate(v)]));
  return value;
}
export function createRaimoAuthGateway(d: GatewayDependencies) {
  const now = d.now || Date.now;
  return async (req: Request): Promise<Response> => {
    const origin = req.headers.get('origin');
    const headers = { 'Content-Type': 'application/json', 'Cache-Control': 'no-store', 'Vary': 'Origin',
      ...(origin === d.origin ? { 'Access-Control-Allow-Origin': d.origin, 'Access-Control-Allow-Headers': 'authorization, content-type', 'Access-Control-Allow-Methods': 'GET, POST, PUT, OPTIONS' } : {}) };
    const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers });
    if (origin && origin !== d.origin) return json({ error: 'forbidden_origin' }, 403);
    if (req.method === 'OPTIONS') return new Response(null, { status: 204, headers });
    try {
      const url = new URL(req.url), path = url.pathname;
      // Keep paths canonical; no query-based credentials, actors or alternate route syntax.
      if (url.search || /%|\/\//.test(path)) return json({ error: 'invalid_request' }, 400);
      const text = await req.text();
      if (text.length > 65536) return json({ error: 'request_too_large' }, 413);
      let input: Record<string, unknown> = {};
      if (text) {
        try { input = JSON.parse(text); } catch { return json({ error: 'invalid_request' }, 400); }
        if (!input || typeof input !== 'object' || Array.isArray(input)) return json({ error: 'invalid_request' }, 400);
      }
      const publicPaths=['/auth/register','/auth/reregister','/auth/register-roster','/auth/reregister-roster','/auth/reset-password/check','/auth/forgot-password/issue','/auth/forgot-password/validate','/auth/reset-password','/notify/registration','/notify/password-reset'];
      if(req.method==='POST' && publicPaths.includes(path) && d.publicAction) return json(await d.publicAction(path,input));
      if (req.method === 'POST' && path === '/auth/login') {
        const email = String(input.email || '').trim().toLowerCase();
        const password = String(input.password_hash || '');
        if (!email || !password || email.length > 320 || password.length > 1024) return json({ error: 'invalid_credentials' }, 401);
        if (!await d.allowLogin(email)) return json({ error: 'try_later' }, 429);
        const user = await d.authenticate(email, password);
        if (!approved(user)) return json({ error: 'invalid_credentials' }, 401);
        const token = Array.from(crypto.getRandomValues(new Uint8Array(32)), b => b.toString(16).padStart(2, '0')).join('');
        await d.sessions.put(token, { uid: user.id, authVersion: user.authVersion, expires: now() + 28800000 });
        return json({ user: publicUser(user), auth_token: token, expires_in: 28800 });
      }
      const authorization = req.headers.get('authorization') || '';
      const token = /^Bearer ([0-9a-f]{64})$/.exec(authorization)?.[1];
      const session = token ? await d.sessions.get(token) : null;
      if (!session || session.expires <= now()) return json({ error: 'login_required' }, 401);
      if (path === '/auth/logout' && req.method === 'POST') {
        await d.sessions.delete(token!); return json({ ok: true });
      }
      const user = await d.member(session.uid);
      if (!approved(user) || user.id !== session.uid || user.authVersion !== session.authVersion) return json({ error: 'membership_required' }, 403);
      const historyRefs=/^\/chat-sessions\/([a-zA-Z0-9_-]+)\/reference-events$/.exec(path);
      if(historyRefs&&req.method==='GET'&&d.referenceEvents){
        if(await d.chatOwner(historyRefs[1])!==user.id)return json({error:'forbidden'},403);
        return json(stripPrivate(await d.referenceEvents(user.id,historyRefs[1])));
      }
      const answerJob=/^\/chat-sessions\/([a-zA-Z0-9_-]+)\/answer-jobs(?:\/([0-9a-f-]+))?$/.exec(path);
      if(answerJob && d.jobs){
        if(await d.chatOwner(answerJob[1])!==user.id)return json({error:'forbidden'},403);
        const raw=new Uint8Array(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(token!)));
        const actor={id:user.id,authVersion:user.authVersion,sessionRef:Array.from(raw,b=>b.toString(16).padStart(2,'0')).join('')};
        if(req.method==='POST'&&!answerJob[2])return json(stripPrivate(await d.jobs.start(actor,answerJob[1],input)),202);
        if(req.method==='GET'&&answerJob[2])return json(stripPrivate(await d.jobs.get(actor,answerJob[1],answerJob[2])));
        return json({error:'invalid_answer_request'},400);
      }
      // 本人に見えている改善機能だけを返す。読めなければ全部オフ（今の画面のまま）。
      if(path==='/features' && req.method==='GET'){
        let flags:FeatureFlag[]=[];
        try{flags=d.featureFlags?await d.featureFlags():[];}catch{flags=[];}
        return json(featuresFor(Array.isArray(flags)?flags:[],{id:user.id,email:user.email}));
      }
      // (2) 回答の評価。スイッチで見えない人には「無い」と同じ 404。本文はサーバーが本人のチャットから引く。
      if(path==='/answer-feedback' && req.method==='POST'){
        let flags:FeatureFlag[]=[];
        try{flags=d.featureFlags?await d.featureFlags():[];}catch{flags=[];}
        requireFeature(Array.isArray(flags)?flags:[],'answer_feedback',{id:user.id,email:user.email});
        if(!d.saveFeedback)return json({error:'feature_not_available'},404);
        const f=parseFeedback(input);
        if(await d.chatOwner(f.chat_id)!==user.id)return json({error:'forbidden'},403);
        const chat=await d.forward('GET','/chat-sessions/'+f.chat_id,{actor_user_id:user.id}) as {messages?:unknown};
        await d.saveFeedback(feedbackRow(user.id,f,Array.isArray(chat?.messages)?chat.messages:[]));
        return json({ok:true});
      }
      // (2) 評価の一覧（運営分析）。管理者で、かつスイッチで見える人だけ。会員の名前・IDは返さない。
      if(path==='/admin/answer-feedback/list' && req.method==='POST'){
        let flags:FeatureFlag[]=[];
        try{flags=d.featureFlags?await d.featureFlags():[];}catch{flags=[];}
        requireFeature(Array.isArray(flags)?flags:[],'answer_feedback',{id:user.id,email:user.email});
        if(!['admin','master_admin'].includes(user.role))return json({error:'forbidden'},403);
        if(!d.listFeedback)return json({error:'feature_not_available'},404);
        const rows=(await d.listFeedback()).map((r:any)=>({rating:r.rating,comment:r.comment,question:r.question,answer:String(r.answer||'').slice(0,400),updated_at:r.updated_at}));
        return json({feedback:rows});
      }
      if(path==='/reference-metadata' && req.method==='GET' && d.referenceMetadata)return json(await d.referenceMetadata());
      // This legacy browser search credential is separate from every privileged server secret.
      if(path==='/semantic-search-config' && req.method==='POST' && d.semanticConfig)return json(await d.semanticConfig());
      if (path === '/auth/attachment-session' && req.method === 'POST') {
        // Identity comes solely from the verified session; input password/user/role ignored.
        const digest = new Uint8Array(await crypto.subtle.digest('SHA-256', new TextEncoder().encode(token!)));
        const parentSession = Array.from(digest, b => b.toString(16).padStart(2, '0')).join('');
        return json(await d.attachmentSession(user.id, parentSession));
      }
      const level = permission(req.method, path);
      if (!level) return json({ error: 'route_not_reviewed' }, 403);
      if ((level === 'staff' && !['admin', 'master_admin'].includes(user.role)) ||
          (level === 'master' && user.role !== 'master_admin')) return json({ error: 'forbidden' }, 403);
      if (level === 'own-list' && path.split('/')[2] !== user.id) return json({ error: 'forbidden' }, 403);
      if (level === 'chat' && await d.chatOwner(path.split('/')[2]) !== user.id) return json({ error: 'forbidden' }, 403);
      // Never forward browser-supplied credentials, internal secrets or actor identity.
      if (path.endsWith('/set-role') && !['user','admin'].includes(String(input.role))) return json({error:'invalid_role'},400);
      if (/^\/admin\/role-requests\/[^/]+\/approve$/.test(path) && !['user','admin'].includes(String(input.new_role))) return json({error:'invalid_role'},400);
      // A chat message's speaker is not the user's membership/administrative role.
      const appendMessage=req.method==='POST' && /^\/chat-sessions\/[a-zA-Z0-9_-]+\/messages-append$/.test(path);
      if(appendMessage && !['user','assistant'].includes(input.role as string))return json({error:'invalid_message_role'},400);
      const forwarded = { ...input };
      for (const key of ['actor_user_id', 'user_id', 'role', 'status', 'secret', '__gateway_secret', 'password_hash', 'auth_token']) delete forwarded[key];
      if(path.endsWith('/set-role') || appendMessage)forwarded.role=input.role;
      forwarded.actor_user_id = user.id;
      if(path.startsWith('/admin/'))forwarded.actor_email = user.email;
      if(path==='/admin/master-transfer/start')forwarded.from_email=user.email;
      if (path === '/chat-sessions') forwarded.user_id = user.id;
      const result = await d.forward(req.method, path, forwarded);
      return json(req.method === 'GET' && ['/admin/users','/admin/users/pending'].includes(path) ? safeUsers(result) : stripPrivate(result));
    } catch (err) {
      const e=err as {code?:string;status?:number};
      if(e && ['feature_not_available','invalid_feedback','invalid_request','email_taken','not_on_roster','already_registered','invalid_token','not_approved','user_not_found','forbidden','member_not_found','invalid_password','try_later','route_not_reviewed','operation_failed','invalid_answer_request','answer_request_conflict','answer_in_progress','answer_not_found','answer_unavailable'].includes(e.code||'')) return json({error:e.code,errorCode:e.code},[400,403,404,409,429,503].includes(e.status||0)?e.status:400);
      // Neither upstream response bodies nor credential/session values are exposed.
      return json({ error: 'service_unavailable' }, 503);
    }
  };
}
