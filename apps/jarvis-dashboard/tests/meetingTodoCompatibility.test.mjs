import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createRequire} from 'node:module';
import test from 'node:test';
import ts from 'typescript';
const realRequire=createRequire(import.meta.url);
function load(file,deps) {
 const src=readFileSync(new URL('../lib/'+file,import.meta.url),'utf8');
 const js=ts.transpileModule(src,{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText;
 const exp={};new Function('require','exports',js)(name=>deps[name]??realRequire(name),exp);return exp;
}
test('payload keeps candidate id and legacy shape remains readable',()=>{
 const action=load('todoist312SlackAction.ts',{
  'next/server':{NextResponse:class{}},'@/lib/meetingTodoAction':{},'@/lib/meetingTodoDeps':{},
  '@/lib/todoistTasks':{},'@/lib/ownerDecisionLog':{}
 });
 const old={n:1,lane:'ai_raimo',title:'Synthetic task',origin:'sb'};
 assert.equal(action.decodeT312Proposal(action.encodeT312Proposal(old)).title,old.title);
 const id='b'.repeat(64),p={...old,candidate_id:id};
 assert.equal(action.decodeT312Proposal(action.encodeT312Proposal(p)).candidate_id,id);
 assert.equal(action.decodeT312Proposal(action.b64urlEncode(JSON.stringify({...old,candidate_id:'bad'}))),null);
});
test('strict dedupe failure and incomplete pagination stop writes; legacy fallback unchanged',async()=>{
 const api=load('todoistTasks.ts',{
  '@/lib/todoistMark':{markTodoistTitle:(s)=>s,stripTodoistMark:(s)=>s},
  '@/lib/todoistProjects':{loadTodoistLaneConfig:()=>({projectId:'test',initialSection:'new',sectionIds:{new:'section'},laneLabel:'synthetic'})}
 });
 const oldFetch=global.fetch,oldToken=process.env.TODOIST_API_TOKEN;
 process.env.TODOIST_API_TOKEN='synthetic';let writes=0;
 try {
  global.fetch=async(_url,options)=>{
   if(options.method==='POST'){writes++;return {ok:true,json:async()=>({id:'t'})}}
   return {ok:false,status:503,text:async()=>''};
  };
  assert.equal((await api.createTodoistTask('ai_raimo',{title:'Synthetic',strictDedupe:true})).ok,false);assert.equal(writes,0);
  assert.equal((await api.createTodoistTask('ai_raimo',{title:'Synthetic'})).ok,true);assert.equal(writes,1);
  writes=0;
  global.fetch=async(_url,options)=>{
   if(options.method==='POST'){writes++;throw Error('unexpected write')}
   return {ok:true,json:async()=>({results:[],next_cursor:'more'})};
  };
  assert.equal((await api.createTodoistTask('ai_raimo',{title:'Synthetic',strictDedupe:true})).ok,false);assert.equal(writes,0);
 } finally {global.fetch=oldFetch;if(oldToken===undefined)delete process.env.TODOIST_API_TOKEN;else process.env.TODOIST_API_TOKEN=oldToken;}
});
