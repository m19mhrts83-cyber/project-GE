import { NextResponse } from "next/server";
import { createClient } from "@/lib/supabase/server";
import { buildInquiryPreview } from "@/lib/reInquiryPreview";

export async function GET(
  _req: Request,
  ctx: { params: Promise<{ id: string }> }
) {
  const { id } = await ctx.params;
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) {
    return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  }

  const { data: row, error } = await supabase
    .from("kurashift_re_deals")
    .select("id, title, source, area, price_man, summary_json")
    .eq("id", id)
    .maybeSingle();

  if (error) {
    return NextResponse.json({ error: error.message }, { status: 500 });
  }
  if (!row) {
    return NextResponse.json({ error: "not found" }, { status: 404 });
  }

  const sj =
    row.summary_json && typeof row.summary_json === "object"
      ? (row.summary_json as Record<string, unknown>)
      : null;

  const preview = buildInquiryPreview({
    title: String(row.title || "物件"),
    summaryJson: sj,
    fromRaw: typeof sj?.from === "string" ? sj.from : null,
    dealId: String(row.id),
    source: row.source != null ? String(row.source) : null,
    area: row.area != null ? String(row.area) : null,
    priceMan: row.price_man != null ? Number(row.price_man) : null,
  });

  return NextResponse.json({
    deal_id: row.id,
    ...preview,
    from_account: "estate",
  });
}
