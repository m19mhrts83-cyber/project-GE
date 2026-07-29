import { NextRequest, NextResponse } from "next/server";
import { supabaseAdmin } from "@/lib/supabaseAdmin";

export const runtime = "nodejs";

function authorized(req: NextRequest): boolean {
  const expected =
    process.env.ANALYTICS_DASHBOARD_SECRET?.trim() ||
    process.env.SEMANTIC_SEARCH_SHARED_SECRET?.trim() ||
    "";
  if (!expected) return false;
  const header =
    req.headers.get("x-analytics-secret")?.trim() ||
    req.headers.get("x-semantic-shared-secret")?.trim() ||
    "";
  const bearer = req.headers.get("authorization")?.replace(/^Bearer\s+/i, "").trim() || "";
  return header === expected || bearer === expected;
}

export async function GET(req: NextRequest) {
  if (!authorized(req)) {
    return NextResponse.json({ errorMessage: "forbidden" }, { status: 403 });
  }

  const days = Math.max(1, Math.min(90, Number(req.nextUrl.searchParams.get("days") || 14)));
  const since = new Date(Date.now() - days * 24 * 60 * 60 * 1000).toISOString();

  try {
    const sb = supabaseAdmin();
    const { data: events, error } = await sb
      .from("app_qa_search_events")
      .select(
        "id,created_at,search_mode,query_text,session_id,comment_hit_count,chunk_hit_count,answer_comment_count,answer_chunk_count"
      )
      .gte("created_at", since)
      .order("created_at", { ascending: false })
      .limit(2000);

    if (error) {
      return NextResponse.json({ errorMessage: error.message }, { status: 500 });
    }

    const rows = events || [];
    let normal = 0;
    let semantic = 0;
    const byDay: Record<string, { normal: number; semantic: number }> = {};
    const queryCounts: Record<string, { count: number; semantic: number; normal: number }> = {};

    for (const row of rows) {
      const mode = String(row.search_mode || "");
      if (mode === "semantic") semantic += 1;
      else if (mode === "normal") normal += 1;

      const day = String(row.created_at || "").slice(0, 10) || "unknown";
      if (!byDay[day]) byDay[day] = { normal: 0, semantic: 0 };
      if (mode === "semantic") byDay[day].semantic += 1;
      else if (mode === "normal") byDay[day].normal += 1;

      const q = String(row.query_text || "")
        .trim()
        .replace(/\s+/g, " ")
        .slice(0, 120);
      if (q) {
        if (!queryCounts[q]) queryCounts[q] = { count: 0, semantic: 0, normal: 0 };
        queryCounts[q].count += 1;
        if (mode === "semantic") queryCounts[q].semantic += 1;
        else queryCounts[q].normal += 1;
      }
    }

    const total = normal + semantic;
    return NextResponse.json({
      ok: true,
      range_days: days,
      since,
      totals: {
        total,
        normal,
        semantic,
        semantic_ratio: total > 0 ? Number((semantic / total).toFixed(4)) : 0,
        normal_ratio: total > 0 ? Number((normal / total).toFixed(4)) : 0,
      },
      daily: Object.keys(byDay)
        .sort()
        .map((day) => ({
          day,
          normal: byDay[day].normal,
          semantic: byDay[day].semantic,
          total: byDay[day].normal + byDay[day].semantic,
        })),
      top_queries: Object.entries(queryCounts)
        .map(([query, v]) => ({ query, ...v }))
        .sort((a, b) => b.count - a.count)
        .slice(0, 30),
      recent_events: rows.slice(0, 40),
    });
  } catch (e: unknown) {
    const message = e instanceof Error ? e.message : String(e);
    return NextResponse.json({ errorMessage: message }, { status: 500 });
  }
}
