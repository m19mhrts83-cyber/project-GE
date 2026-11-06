import test from 'node:test';
import assert from 'node:assert/strict';
import {createProductionAdapter} from '../lib/raimoAuthAdapter.ts';
const config={origin:'https://app.example',raimoBase:'https://app.example/miniAppApi/test',gatewaySecret:'g'.repeat(40),proxySecret:'p'.repeat(40),projectUrl:'https://fixture.supabase.co',serviceKey:'service-only'};
test('comment page adapter fixes the upstream route and projects only approved display fields',async()=>{
 let call;
 const adapter=createProductionAdapter(config,async()=>false,async()=>'',async(url,options)=>{call={url,body:JSON.parse(options.body)};return Response.json({comments:[{id:501,comment_id:'42',content:'display',posted_at:'2025-01-01',author_email:'private',ip_address:'private',password_hash:'private',secret:'private'}]});});
 const result=await adapter.deps.forward('POST','/comments-page',{after_id:500,limit:50000,secret:'forged'});
 assert.equal(call.url,config.raimoBase+'/internal/read/comments-page');assert.deepEqual(call.body,{after_id:500,__gateway_secret:config.gatewaySecret});
 assert.deepEqual(result,{comments:[{id:501,comment_id:'42',posted_at:'2025-01-01',content:'display'}]});
});
test('invalid page cursors never reach the backend',async()=>{
 let calls=0;const adapter=createProductionAdapter(config,async()=>false,async()=>'',async()=>{calls++;throw new Error('unexpected');});
 for(const after_id of [-1,0.5,'1 OR 1=1',Number.MAX_SAFE_INTEGER+1])await assert.rejects(adapter.deps.forward('POST','/comments-page',{after_id}),e=>e.code==='invalid_request');
 assert.equal(calls,0);
});
