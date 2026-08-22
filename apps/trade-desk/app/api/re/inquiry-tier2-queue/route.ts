import { createClient } from "@/lib/supabase/server";
import { getTier2QueueSummary } from "@/lib/reInquiryTier2Queue";
import { NextResponse } from "next/server";

export async function GET() {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) {
    return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  }

  const summary = await getTier2QueueSummary(supabase);
  return NextResponse.json({ ok: true, ...summary });
}
