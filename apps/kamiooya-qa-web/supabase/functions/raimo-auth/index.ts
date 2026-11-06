declare const EdgeRuntime:{waitUntil(task:Promise<unknown>):void};
import {handleSemanticSearch} from '../semantic-search/handler.ts';
import bcrypt from 'npm:bcryptjs@3.0.3';
import { createRaimoAuthGateway } from '../../../lib/raimoAuthGateway.ts';
import { createProductionAdapter, digest } from '../../../lib/raimoAuthAdapter.ts';
const origin='https://ma-54t2keqdelz3.raimo-app.buzz';
const config={origin,normalPipelineV2:Deno.env.get('RAIMO_NORMAL_PIPELINE_V2')!=='0',projectUrl:Deno.env.get('SUPABASE_URL')||'',serviceKey:Deno.env.get('SUPABASE_SERVICE_ROLE_KEY')||'',
 raimoBase:origin+'/miniAppApi/be_nXbcTm3EumRbotHtAwGGXb45raHz0',gatewaySecret:Deno.env.get('RAIMO_AUTH_GATEWAY_SECRET')||'',proxySecret:Deno.env.get('COMMUNITY_ATTACHMENTS_PROXY_SECRET')||''};
const verify=async(raw:string,stored:string)=>{
 if(/^\$2[aby]\$\d{2}\$/.test(stored))return bcrypt.compare(raw,stored);
 if(/^[0-9a-f]{64}$/i.test(stored))return await digest(raw)===stored.toLowerCase();
 return stored.length>0 && await digest(raw)===await digest(stored);
};
Deno.serve(async(req:Request)=>{
 try{
  const adapter=createProductionAdapter(config,verify,raw=>bcrypt.hash(raw,12),fetch,{schedule:task=>EdgeRuntime.waitUntil(task),semantic:handleSemanticSearch});
  const path=new URL(req.url).pathname.replace(/^\/raimo-auth|^\/functions\/v1\/raimo-auth/,'')||'/';
  if(path==='/internal/attachment-user-status'){
   if(req.method!=='POST'||Number(req.headers.get('content-length')||0)>16384)return Response.json({error:'unauthorized'},{status:401});
   const text=await req.text();if(text.length>16384)return Response.json({error:'request_too_large'},{status:413});
   const body=JSON.parse(text);
   if(await digest(String(body.secret||''))!==await digest(config.proxySecret))return Response.json({error:'unauthorized'},{status:401});
   return Response.json(await adapter.status(String(body.user_id||''),String(body.session_ref||'')),{headers:{'Cache-Control':'no-store'}});
  }
  // Gateway-level rate limit bounds abuse of unknown accounts as well as account-specific limits.
  // Preflight is cheap and must not consume login attempts.
  if(req.method!=='OPTIONS' && path.startsWith('/auth/')){
   const ip=(req.headers.get('x-forwarded-for')||'unknown').split(',')[0].trim().slice(0,100);
   if(!await adapter.allow('ip:'+ip,50))return Response.json({error:'try_later'},{status:429,headers:{'Access-Control-Allow-Origin':origin,'Cache-Control':'no-store'}});
  }
  const url=new URL(req.url);url.pathname=path;
  return await createRaimoAuthGateway(adapter.deps)(new Request(url,req));
 }catch{
  return Response.json({error:'service_unavailable'},{status:503,headers:{'Cache-Control':'no-store','Access-Control-Allow-Origin':origin}});
 }
});
