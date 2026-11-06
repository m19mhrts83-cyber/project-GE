import test from 'node:test';
import assert from 'node:assert/strict';
import {decodeNormalAnswer} from '../lib/normalAnswerEnvelope.ts';
const context={relatedComments:[{comment_id:'42',content:'unchanged'}],relatedLessonComments:[{comment_id:'lesson'}],relatedChunks:[{chunk_key:'video',start_sec:61}]};
const good={answer:'回答',used_sources:{comment_ids:['42','lesson'],chunk_keys:['video']}};
test('structured answer preserves selected evidence and accepts only supplied IDs',()=>{
 const result=decodeNormalAnswer({...context,response:JSON.stringify(good)});assert.equal(result.answer,'回答');assert.deepEqual(JSON.parse(result.usedSources),good.used_sources);assert.deepEqual(result.relatedComments,context.relatedComments);assert.deepEqual(result.relatedChunks,context.relatedChunks);
 assert.equal(decodeNormalAnswer({...context,response:'```json\n'+JSON.stringify(good)+'\n```'}).answer,'回答');
});
test('malformed answers, invented sources and unsupported answers require compatibility fallback',()=>{
 for(const response of ['not JSON',{}, {...good,answer:''},{...good,used_sources:{comment_ids:['invented'],chunk_keys:[]}},{...good,used_sources:{comment_ids:[],chunk_keys:[]}}])assert.throws(()=>decodeNormalAnswer({...context,response}));
});
test('duplicates normalize and an explicit no-evidence refusal remains valid',()=>{
 assert.deepEqual(JSON.parse(decodeNormalAnswer({...context,response:{...good,used_sources:{comment_ids:[42,'42'],chunk_keys:[]}}}).usedSources).comment_ids,['42']);
 assert.equal(decodeNormalAnswer({...context,response:{answer:'参照内で確証が取れないため、お答えすることができません。',used_sources:{comment_ids:[],chunk_keys:[]}}}).answer.includes('確証'),true);
});
