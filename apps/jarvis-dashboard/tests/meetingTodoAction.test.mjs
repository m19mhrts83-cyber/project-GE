import assert from 'node:assert/strict';
import test from 'node:test';
import {applyMeetingTodo} from '../lib/meetingTodoAction.ts';
const id='a'.repeat(64);
function setup(changes={}) {
 let raw=JSON.stringify({candidate_id:id,meeting_id:'synthetic',todo:'Task',title:'Task',lane:'ai_raimo',
   owner_confirmed:true,extracted:true,notion_page_id:'page',notion_url:'https://example.test/minutes',assignee:'owner',evidence:'explicit',status:'posted',...changes});
 const calls={create:0,finish:0,fail:0};
 const d={read:async()=>raw,cas:async(_id,old,row)=>{if(old!==raw)return false;raw=JSON.stringify(row);return true},
   create:async()=>{calls.create++;await new Promise(r=>setImmediate(r));return {ok:true,id:'task',url:'https://example.test/task'}},
   finish:async()=>{calls.finish++},fail:async()=>{calls.fail++}};
 return {d,calls,row:()=>JSON.parse(raw)};
}
test('only one concurrent click creates and repeat is terminal',async()=>{
 const x=setup(); const r=await Promise.all([applyMeetingTodo(id,'create',x.d),applyMeetingTodo(id,'create',x.d)]);
 assert.equal(x.calls.create,1);assert.equal(x.calls.finish,1);assert.equal(r.filter(r=>r.ok).length,1);
 assert.equal((await applyMeetingTodo(id,'create',x.d)).ok,true);assert.equal(x.calls.create,1);
});
test('dismiss is permanent and prevents later create',async()=>{
 const x=setup();assert.equal((await applyMeetingTodo(id,'dismiss',x.d)).ok,true);
 await applyMeetingTodo(id,'create',x.d);assert.equal(x.calls.create,0);assert.equal(x.row().status,'dismissed');
});
test('unknown owner, held, unsaved and malformed id cannot create',async()=>{
 for(const changes of [{owner_confirmed:false},{notion_page_id:''},{extracted:false},{status:'held'},{evidence:''}]){
  const x=setup(changes);assert.equal((await applyMeetingTodo(id,'create',x.d)).ok,false);assert.equal(x.calls.create,0);
 }
 assert.equal((await applyMeetingTodo('bad','create',setup().d)).ok,false);
});
test('API failure or timeout cannot auto-create twice',async()=>{
 for(const throws of [true,false]){
  const x=setup();x.d.create=async()=>{x.calls.create++;if(throws)throw Error('timeout');return {ok:false,error:'dedupe unavailable'}};
  assert.equal((await applyMeetingTodo(id,'create',x.d)).ok,false);
  await applyMeetingTodo(id,'create',x.d);assert.equal(x.calls.create,1);assert.equal(x.row().status,'uncertain');
 }
});
test('comment/log/notification failure preserves task id and blocks recreation',async()=>{
 const x=setup();x.d.finish=async()=>{throw Error('comment failed')};
 assert.equal((await applyMeetingTodo(id,'create',x.d)).ok,false);assert.equal(x.row().task_id,'task');
 await applyMeetingTodo(id,'create',x.d);assert.equal(x.calls.create,1);assert.equal(x.calls.fail,1);
});
test('durable store failure stops before any create',async()=>{
 const x=setup();x.d.read=async()=>{throw Error('offline')};
 assert.equal((await applyMeetingTodo(id,'create',x.d)).ok,false);assert.equal(x.calls.create,0);
});
test('already-created record never creates again or becomes dismissed',async()=>{
 const x=setup({status:'created',task_id:'existing',task_url:'https://example.test/task'});
 assert.equal((await applyMeetingTodo(id,'dismiss',x.d)).ok,false);
 assert.equal((await applyMeetingTodo(id,'create',x.d)).ok,true);assert.equal(x.calls.create,0);
});
