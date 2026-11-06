import test from 'node:test';
import assert from 'node:assert/strict';
import {decodeNormalAnswer} from '../lib/normalAnswerEnvelope.ts';
const context={relatedComments:[{comment_id:'42',content:'unchanged'}],relatedLessonComments:[{comment_id:'lesson'}],relatedChunks:[{chunk_key:'video',start_sec:61}]};
test('ordinary Markdown survives while actual evidence IDs become stable UI citations',()=>{
 const result=decodeNormalAnswer({...context,response:'### 工夫\n- 内容〔コメントID:42〕〔コメントID:lesson〕\n- 動画1:01〔チャンクID:video〕'});
 assert.equal(result.answer,'### 工夫\n- 内容[コミュニティ1][コミュニティ2]\n- 動画1:01[セミナー1]');assert.deepEqual(JSON.parse(result.usedSources),{comment_ids:['42','lesson'],chunk_keys:['video']});assert.equal(result.relatedComments[0].content,'unchanged');assert.equal(result.relatedChunks[0].start_sec,61);
});
test('missing, malformed and invented references require compatibility fallback',()=>{
 for(const response of ['no markers',null,'', '本文〔コメントID:invented〕','本文〔コメントID:42', '本文〔コメントID:42〕〔チャンクID:invented〕'])assert.throws(()=>decodeNormalAnswer({...context,response}));
});
test('duplicates preserve first mention order and explicit no-evidence refusal is accepted',()=>{
 const result=decodeNormalAnswer({...context,response:'本文〔コメントID:lesson〕〔コメントID:42〕〔コメントID:42〕'});assert.deepEqual(JSON.parse(result.usedSources).comment_ids,['lesson','42']);
 assert.equal(decodeNormalAnswer({...context,response:'参照内で確証が取れないため、お答えすることができません。'}).answer.includes('確証'),true);
});
test('internal DB IDs normalize only when the provided source identity is unambiguous',()=>{
 const source={...context,relatedComments:[{id:900,comment_id:'42',content:'same evidence'}]};
 assert.deepEqual(JSON.parse(decodeNormalAnswer({...source,response:'本文〔コメントID:900〕'}).usedSources).comment_ids,['42']);
 const collision={...source,relatedComments:[...source.relatedComments,{id:42,comment_id:'other',content:'different evidence'}]};
 assert.throws(()=>decodeNormalAnswer({...collision,response:'本文〔コメントID:42〕'}),/ambiguous/);
});
