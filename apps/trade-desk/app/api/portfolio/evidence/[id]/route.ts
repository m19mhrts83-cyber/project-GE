import { createClient } from '@/lib/supabase/server';
import { evidenceImage } from '@/lib/asset618Image';
export const dynamic = 'force-dynamic';
export async function GET(_request: Request, {params}: {params: Promise<{id: string}>}) {
  const client = await createClient();
  const {data:{user}} = await client.auth.getUser();
  return evidenceImage(client,user?.id || null,(await params).id);
}
