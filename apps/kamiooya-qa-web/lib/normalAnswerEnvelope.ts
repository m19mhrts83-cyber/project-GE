import {labelAnswerSources,attachReferenceLabels} from './searchReferences.ts';
// Keep the ordinary Markdown answer. Extract model-supplied evidence markers
// deterministically; unknown/malformed markers require the legacy fallback.
export function decodeNormalAnswer(value:any){
 const rows=(v:any)=>{if(typeof v==='string')v=JSON.parse(v);if(!Array.isArray(v))throw new Error('invalid_normal_context');return v;};
 const comments=rows(value.relatedComments),lessons=rows(value.relatedLessonComments),chunks=rows(value.relatedChunks);
 if(typeof value.response!=='string'||!value.response.trim())throw new Error('invalid_normal_answer');
 const labels=labelAnswerSources([...comments,...lessons],chunks,[]);
 // Raimo rows expose both an internal DB id and the original comment_id.
 // Resolve only one-to-one aliases from the supplied rows; collisions fail closed.
 const aliases=new Map<string,Set<string>>();
 for(const row of [...comments,...lessons])for(const key of ['comment_id','id']){
  if(row[key]==null||row.comment_id==null)continue;
  const alias=String(row[key]);if(!aliases.has(alias))aliases.set(alias,new Set());aliases.get(alias)!.add(String(row.comment_id));
 }
 const commentIds=new Set<string>(),chunkKeys=new Set<string>();
 const answer=value.response.replace(/〔(コメントID|チャンクID):([^〕]+)〕/g,(_:string,kind:string,id:string)=>{
  if(kind==='コメントID'){
   const candidates=aliases.get(id);if(!candidates||candidates.size!==1)throw new Error('ambiguous_normal_source');
   id=[...candidates][0];
  }
  const map=kind==='コメントID'?labels.comments:labels.chunks;
  if(!Object.hasOwn(map,id))throw new Error('unknown_normal_source');
  (kind==='コメントID'?commentIds:chunkKeys).add(id);
  return '['+map[id]+']';
 }).trim();
 if(!answer||/〔(?:コメントID|チャンクID)/.test(answer))throw new Error('invalid_normal_answer');
 if(!commentIds.size&&!chunkKeys.size&&(comments.length||lessons.length||chunks.length)&&!answer.includes('参照内で確証が取れないため'))throw new Error('missing_normal_sources');
 return {pipeline:'normal-v2',answer,usedSources:JSON.stringify({comment_ids:[...commentIds],chunk_keys:[...chunkKeys]}),relatedComments:attachReferenceLabels(comments,'comment_id',labels.comments),relatedLessonComments:attachReferenceLabels(lessons,'comment_id',labels.comments),relatedChunks:attachReferenceLabels(chunks,'chunk_key',labels.chunks),relatedSources:[],referenceLabels:labels,referenceSelection:commentIds.size||chunkKeys.size?'mentioned':'provided-context'};
}
