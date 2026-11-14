import type { SupabaseClient } from '@supabase/supabase-js';
import { assetOwner } from './asset618Server';
import { EVIDENCE_BUCKET, evidencePath, SHA, UUID } from './asset618Contract';
export async function evidenceImage(client: SupabaseClient, userId: string | null, id: string): Promise<Response> {
  const headers = {'Cache-Control':'private, no-store, max-age=0','X-Content-Type-Options':'nosniff','Vary':'Cookie'};
  const fail = (status: number) => new Response('証拠画像を取得できません',{status,headers});
  if (!userId) return fail(401);
  if (!UUID.test(id)) return fail(404);
  const owner = await assetOwner(client,userId);
  if (owner === null) return fail(503);
  if (!owner) return fail(403);
  try {
    const {data,error} = await client.from('asset_evidence_latest').select('owner_id,account_scope,account_id,contract_key,view_key,active_slot,storage_path,sha256').eq('id',id).eq('owner_id',userId).limit(1);
    if (error) return fail(503);
    const row = data?.[0];
    if (!row || row.owner_id !== userId || !row.storage_path || row.storage_path !== evidencePath(row) || !SHA.test(row.sha256 || '')) return fail(404);
    const {data: image,error: imageError} = await client.storage.from(EVIDENCE_BUCKET).download(row.storage_path);
    if (imageError || !image || image.size > 10 * 1024 * 1024) return fail(503);
    const bytes = Buffer.from(await image.arrayBuffer());
    if (createImageHash(bytes) !== row.sha256 || !bytes.subarray(0,8).equals(Buffer.from([137,80,78,71,13,10,26,10]))) return fail(409);
    return new Response(new Uint8Array(bytes),{headers:{...headers,'Content-Type':'image/png','Content-Disposition':'inline; filename="asset-evidence.png"'}});
  } catch { return fail(503); }
}
import { createHash } from 'node:crypto';
const createImageHash = (bytes: Uint8Array) => createHash('sha256').update(bytes).digest('hex');
