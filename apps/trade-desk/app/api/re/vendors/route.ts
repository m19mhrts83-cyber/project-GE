import { createClient } from "@/lib/supabase/server";
import { NextResponse } from "next/server";

export async function GET(req: Request) {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) {
    return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  }

  const url = new URL(req.url);
  const filter = (url.searchParams.get("filter") || "all").trim();

  let q = supabase
    .from("kurashift_re_vendors")
    .select("*")
    .order("contacted_at", { ascending: false, nullsFirst: false })
    .order("updated_at", { ascending: false })
    .limit(500);

  if (filter === "pending") {
    q = q.in("status", ["pending", "discovered"]);
  } else if (filter === "contacted") {
    q = q.eq("status", "contacted");
  } else if (filter === "replied") {
    q = q.eq("status", "replied");
  } else if (filter === "excluded") {
    q = q.in("status", ["skip", "invalid"]);
  }

  const { data: vendors, error } = await q;
  if (error) {
    return NextResponse.json({ error: error.message }, { status: 500 });
  }

  let rows = vendors || [];
  if (filter === "followup") {
    const now = Date.now();
    rows = rows.filter((v) => {
      if (v.status === "replied") return true;
      if (v.status !== "contacted" || !v.contacted_at) return false;
      const sent = new Date(v.contacted_at).getTime();
      if (Number.isNaN(sent)) return false;
      return (now - sent) / 86400000 >= 7;
    });
  }

  const { data: deals } = await supabase
    .from("kurashift_re_deals")
    .select("id, summary_json")
    .limit(500);

  const dealCountByVendor = new Map<string, number>();
  for (const d of deals || []) {
    const sj =
      d.summary_json && typeof d.summary_json === "object"
        ? (d.summary_json as { vendor_id?: string })
        : {};
    const vid = sj.vendor_id;
    if (vid) {
      dealCountByVendor.set(vid, (dealCountByVendor.get(vid) || 0) + 1);
    }
  }

  const counts: Record<string, number> = {};
  for (const v of vendors || []) {
    const st = v.status || "pending";
    counts[st] = (counts[st] || 0) + 1;
  }

  let latestSync: string | null = null;
  for (const v of vendors || []) {
    const s = v.synced_at as string | undefined;
    if (s && (!latestSync || s > latestSync)) latestSync = s;
  }

  return NextResponse.json({
    ok: true,
    filter,
    total: rows.length,
    by_status: counts,
    latest_sync: latestSync,
    vendors: rows.map((v) => ({
      ...v,
      deal_count: dealCountByVendor.get(v.id) || 0,
    })),
  });
}
