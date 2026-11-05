type Row = Record<string, any>;
export function labelAnswerSources(comments: Row[], chunks: Row[], openchats: Row[]) {
  const commentsById = Object.fromEntries(comments.map((r,i)=>[String(r.comment_id),`コミュニティ${i+1}`]));
  const chunksByKey = Object.fromEntries(chunks.map((r,i)=>[String(r.chunk_key),`セミナー${i+1}`]));
  const openchatsById = Object.fromEntries(openchats.map((r,i)=>[String(r.id),`LINEオプチャ${i+1}`]));
  return {comments: commentsById, chunks: chunksByKey, openchats: openchatsById};
}

export function attachReferenceLabels(rows: Row[], key: string, labels: Record<string,string>) {
  return rows.map(row=>({...row,...(labels[String(row[key])] ? {citation_label:labels[String(row[key])]} : {})}));
}

export function mentionedSourceLabels(answer:string):Set<string>{
 const found=new Set<string>();
 for(const match of answer.matchAll(/(LINEオプチャ|コミュニティ|セミナー)(\d+(?:\s*[、,]\s*\d+)*)/g)){
  for(const index of match[2].split(/[、,]/))found.add(match[1]+Number(index.trim()));
 }
 return found;
}
