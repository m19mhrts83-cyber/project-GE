import { createClient } from '@/lib/supabase/server';
import { confirmDisplay } from '@/lib/asset618Server';
import { NextResponse } from 'next/server';
export const dynamic = 'force-dynamic';
export async function POST(request: Request) {
  const headers = {'Cache-Control':'private, no-store'};
  let sameOrigin = false;
  try {
    const origin = new URL(request.headers.get('origin') || '');
    sameOrigin = ['http:','https:'].includes(origin.protocol) && origin.host === (request.headers.get('host') || new URL(request.url).host);
  } catch { /* fail closed */ }
  if (!sameOrigin) return NextResponse.json({error:'invalid origin'},{status:403,headers});
  const client = await createClient();
  const {data:{user}} = await client.auth.getUser();
  if (!user) return NextResponse.json({error:'unauthorized'},{status:401,headers});
  const body = await request.json().catch(() => null);
  const result = await confirmDisplay(client,user.id,body);
  return NextResponse.json(result.body,{status:result.status,headers});
}
