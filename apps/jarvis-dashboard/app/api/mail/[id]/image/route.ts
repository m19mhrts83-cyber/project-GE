import { NextResponse } from "next/server";
import { createClient } from "@/lib/supabase/server";
import { fetchMailAttachmentBytes } from "@/lib/gmail/fetchMessageParts";

export const runtime = "nodejs";
export const maxDuration = 30;

export async function GET(
  request: Request,
  ctx: { params: Promise<{ id: string }> },
) {
  const { id } = await ctx.params;
  const aid = new URL(request.url).searchParams.get("aid") || "";
  if (!id || !aid) {
    return NextResponse.json({ error: "missing" }, { status: 400 });
  }

  const supabase = await createClient();
  const { data: it } = await supabase
    .from("triage_items")
    .select("id,gmail_message_id,account")
    .eq("id", id)
    .maybeSingle();
  if (!it?.gmail_message_id) {
    return NextResponse.json({ error: "not found" }, { status: 404 });
  }

  const r = await fetchMailAttachmentBytes({
    gmailMessageId: String(it.gmail_message_id),
    attachmentId: aid,
    account: it.account,
  });
  if (!r.ok) {
    return NextResponse.json({ error: r.error }, { status: 404 });
  }
  return new NextResponse(new Uint8Array(r.bytes), {
    status: 200,
    headers: {
      "Content-Type": r.mimeType,
      "Cache-Control": "private, max-age=3600",
    },
  });
}
