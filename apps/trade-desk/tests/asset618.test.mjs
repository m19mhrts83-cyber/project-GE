import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
import {createRequire} from 'node:module';
import ts from 'typescript';
const require=createRequire(import.meta.url),cache=new Map();
function load(name){
 if(cache.has(name))return cache.get(name);
 const code=ts.transpileModule(readFileSync(new URL(`../lib/${name}.ts`,import.meta.url),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText;
 const exports={};cache.set(name,exports);
 vm.runInNewContext(code,{exports,require:path=>path.startsWith('./')?load(path.slice(2)):require(path),Buffer,Response,Blob,Uint8Array,Date,console,URL});return exports;
}
const c=load('asset618Contract'), s=load('asset618Server'), image=load('asset618Image');
const owner='11111111-1111-4111-8111-111111111111',run='22222222-2222-4222-8222-222222222222',proof='33333333-3333-4333-8333-333333333333';
const row={table:'portfolio_snapshots',account_id:'sbi_index',as_of:'2026-11-14',value:'123000',source:'weekly_web'};
class Fake {
 constructor(){this.tables={asset_evidence_owners:[{user_id:owner}],portfolio_accounts:[{id:'sbi_index',name:'テスト証券'}],liquidity_accounts:[],portfolio_snapshots:[{account_id:row.account_id,as_of:row.as_of,value_jpy:row.value,source:row.source}],asset_618_display_checks:[]};this.context={run_id:run,target_ids:['sbi_index','axa_life'],numeric_readbacks:{portfolio_snapshots:{sbi_index:{status:'verified',record_as_of:row.as_of,row_digest:s.digest(c.rowText(row))}}}};this.tables.sync_meta=[{key:'portfolio_weekly_summary',value:JSON.stringify({asset_618:this.context})}];this.errorTable=null;this.blob=new Blob([Buffer.from([137,80,78,71,13,10,26,10,0,0,0])]);this.storage={from:()=>({download:async()=>({data:this.blob,error:null})})};}
 from(name){
  const client=this, filters=[];let posted=null;
  const q={select(){return q;},eq(k,v){filters.push(r=>r[k]===v);return q;},in(k,vs){filters.push(r=>vs.includes(r[k]));return q;},gte(k,v){filters.push(r=>r[k]>=v);return q;},lte(k,v){filters.push(r=>r[k]<=v);return q;},limit(){return q;},upsert(value){posted=value;return q;},then(resolve,reject){
   if(client.errorTable===name)return Promise.resolve({data:null,error:{message:'secret'}}).then(resolve,reject);
   if(posted)client.tables[name]=[posted];
   return Promise.resolve({data:(client.tables[name]||[]).filter(r=>filters.every(f=>f(r))),error:null}).then(resolve,reject);
  }};return q;
 }
}
test('decimal and source/date identity produce the same digest as Python',()=>{assert.equal(c.decimalText('00123.000'),'123');assert.equal(c.decimalText('-0.00'),'0');assert.throws(()=>c.decimalText('NaN'));assert.throws(()=>c.rowText({...row,as_of:'2026-02-30'}));assert.equal(s.digest(c.rowText({...row,value:'123.00'})),'4f857b8c48895b780257e3fcfbecab637ae8bf4ac041bb7799141197cc9a4342');});
test('normal DB rows are compared to per-run readback, preserving unknown source date',async()=>{const status=await s.loadNumericStatus(new Fake(),owner);assert.equal(status.state,'ready');assert.equal(status.rows[0].matches,true);assert.equal(status.rows[0].label,'テスト証券');assert.equal(status.rows[0].source_as_of,null);assert.equal(status.unresolved,1);});
test('missing owner or unavailable metadata fails closed',async()=>{assert.equal((await s.loadNumericStatus(new Fake(),'other')).state,'not_owner');const f=new Fake();f.errorTable='asset_evidence_owners';assert.equal((await s.loadNumericStatus(f,owner)).state,'unavailable');});
test('receipt records matched subset with unresolved targets',async()=>{const f=new Fake();const result=await s.confirmDisplay(f,owner,{run_id:run,rows:[row]});assert.equal(result.status,200);assert.equal(result.body.matched,1);assert.equal(result.body.unresolved,1);assert.equal(f.tables.asset_618_display_checks.length,1);});
test('tampered displayed amount cannot record a match',async()=>{const f=new Fake();assert.equal((await s.confirmDisplay(f,owner,{run_id:run,rows:[{...row,value:'999'}]})).status,409);assert.equal(f.tables.asset_618_display_checks.length,0);});
test('changed DB row cannot reuse prior display confirmation',async()=>{const f=new Fake();f.tables.portfolio_snapshots[0].value_jpy=999;assert.equal((await s.confirmDisplay(f,owner,{run_id:run,rows:[row]})).status,409);});
test('old run, omitted row, duplicates rejected',async()=>{for(const input of [{run_id:proof,rows:[row]},{run_id:run,rows:[]},{run_id:run,rows:[row,row]}])assert.equal((await s.confirmDisplay(new Fake(),owner,input)).status,409);});
test('failed receipt persistence never reports success',async()=>{const f=new Fake();f.errorTable='asset_618_display_checks';assert.equal((await s.confirmDisplay(f,owner,{run_id:run,rows:[row]})).status,503);});
test('old normal image state is explicit on failed or pending updates',()=>{assert.match(c.evidenceState({storage_path:'old',last_attempt_status:'failed'}),/前回/);assert.match(c.evidenceState({storage_path:'old',last_attempt_status:'pending'}),/確認待ち/);assert.equal(c.evidenceState({storage_path:null,last_attempt_status:'failed'}),'正常画像なし');});
async function imageFixture(){const f=new Fake();const r={id:proof,owner_id:owner,account_scope:'portfolio',account_id:'sbi_index',contract_key:'primary',view_key:'balance',active_slot:'a'};r.storage_path=c.evidencePath(r);r.sha256=require('node:crypto').createHash('sha256').update(Buffer.from(await f.blob.arrayBuffer())).digest('hex');f.tables.asset_evidence_latest=[r];return f;}
test('image proxy requires owner and does not use signed URLs',async()=>{const f=await imageFixture();assert.equal((await image.evidenceImage(f,null,proof)).status,401);assert.equal((await image.evidenceImage(f,'other',proof)).status,403);const response=await image.evidenceImage(f,owner,proof);assert.equal(response.status,200);assert.equal(response.headers.get('content-type'),'image/png');assert.match(response.headers.get('cache-control'),/no-store/);});
test('mismatched bytes or wrong storage path never served',async()=>{const f=await imageFixture();f.blob=new Blob(['corrupt']);assert.equal((await image.evidenceImage(f,owner,proof)).status,409);f.tables.asset_evidence_latest[0].storage_path='../other.png';assert.equal((await image.evidenceImage(f,owner,proof)).status,404);});
