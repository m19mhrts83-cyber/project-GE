import { NextResponse } from "next/server";
import { serviceClient } from "@/lib/supabase";
import { addTagsByKey, rememberStayReason } from "@/lib/desk";
import { STAY_REASON_TAGS } from "@/lib/decisionContract";
import { isDeskItemId } from "@/lib/deskCore";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

/** 判断のあとに押された理由（任意）を同じ行に足す */
export async function POST(req: Request) {
  let b: { itemId?: string; idemKey?: string; reasonTags?: string[]; stayReason?: string | null; quality?: string | null; note?: string | null };
  try {
    b = await req.json();
  } catch {
    return NextResponse.json({ ok: false, error: "bad json" }, { status: 400 });
  }
  const key = String(b.idemKey || "");
  if (key.length < 8) return NextResponse.json({ ok: false, error: "idemKey" }, { status: 400 });
  const sb = serviceClient();
  if (!sb) return NextResponse.json({ ok: false, error: "supabase_unconfigured" }, { status: 503 });
  const ok = await addTagsByKey(sb, key, b);
  const id = String(b.itemId || "");
  if (b.stayReason && b.stayReason in STAY_REASON_TAGS && isDeskItemId(id)) {
    await rememberStayReason(sb, id, b.stayReason);
  }
  return NextResponse.json({ ok }, { status: ok ? 200 : 404 });
}
