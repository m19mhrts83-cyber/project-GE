// The model writes the answer and evidence IDs together. Treat both as untrusted:
// invalid envelopes fall back to the unchanged legacy pipeline before any chat write.
export function decodeNormalAnswer(value:any){
 const rows=(v:any)=>{if(typeof v==='string')v=JSON.parse(v);if(!Array.isArray(v))throw new Error('invalid_normal_context');return v;};
 const comments=rows(value.relatedComments),lessons=rows(value.relatedLessonComments),chunks=rows(value.relatedChunks);
 let body=value.response;
 if(typeof body==='string')body=JSON.parse(body.trim().replace(/^```(?:json)?\s*\n?([\s\S]*?)\n?```$/,'$1'));
 if(!body||typeof body.answer!=='string'||!body.answer.trim()||typeof body.used_sources!=='object'||!body.used_sources)throw new Error('invalid_normal_answer');
 const ids=(input:any,allowed:Set<string>)=>{
  if(!Array.isArray(input)||input.some(v=>!['string','number'].includes(typeof v)))throw new Error('invalid_normal_sources');
  const result=[...new Set(input.map(String))];if(result.some(v=>!allowed.has(v)))throw new Error('unknown_normal_source');return result;
 };
 const commentIds=ids(body.used_sources.comment_ids,new Set([...comments,...lessons].map(r=>String(r.comment_id))));
 const chunkKeys=ids(body.used_sources.chunk_keys,new Set(chunks.map(r=>String(r.chunk_key))));
 if(!commentIds.length&&!chunkKeys.length&&(comments.length||lessons.length||chunks.length)&&!body.answer.includes('参照内で確証が取れないため'))throw new Error('missing_normal_sources');
 return {pipeline:'normal-v2',answer:body.answer.trim(),usedSources:JSON.stringify({comment_ids:commentIds,chunk_keys:chunkKeys}),relatedComments:comments,relatedLessonComments:lessons,relatedChunks:chunks,relatedSources:[]};
}
