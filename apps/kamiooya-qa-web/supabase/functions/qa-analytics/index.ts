// Phase 13: Q&A search analytics overview for operators.
// Auth: X-Semantic-Shared-Secret. Deploy with --no-verify-jwt.

import { createClient } from "https://esm.sh/@supabase/supabase-js@2.49.1";

type Body = {
  days?: number;
  secret?: string;
};

function corsHeaders(): HeadersInit {
  return {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Headers":
      "authorization, x-client-info, apikey, content-type, x-semantic-shared-secret",
    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
  };
}

function json(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: { ...corsHeaders(), "Content-Type": "application/json" },
  });
}

function asString(value: unknown): string {
  return typeof value === "string" ? value : value == null ? "" : String(value);
}

function isAuthorized(req: Request, body: Body | null): boolean {
  const expected = (Deno.env.get("SEMANTIC_SEARCH_SHARED_SECRET") || "").trim();
  if (!expected) return true;
  const headerSecret = (req.headers.get("x-semantic-shared-secret") || "").trim();
  const bodySecret = asString(body?.secret).trim();
  const urlSecret = new URL(req.url).searchParams.get("secret") || "";
  return (
    headerSecret === expected ||
    bodySecret === expected ||
    urlSecret === expected
  );
}

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") {
    return new Response("ok", { headers: corsHeaders() });
  }
  if (req.method !== "GET" && req.method !== "POST") {
    return json({ errorMessage: "method_not_allowed" }, 405);
  }

  let body: Body | null = null;
  if (req.method === "POST") {
    body = (await req.json().catch(() => null)) as Body | null;
  }
  if (!isAuthorized(req, body)) {
    return json({ errorMessage: "forbidden" }, 403);
  }

  const daysRaw = body?.days ?? Number(new URL(req.url).searchParams.get("days") || 14);
  const days = Math.max(1, Math.min(90, Number.isFinite(daysRaw) ? daysRaw : 14));

  const supabaseUrl = (Deno.env.get("SUPABASE_URL") || "").trim();
  const serviceKey = (Deno.env.get("SUPABASE_SERVICE_ROLE_KEY") || "").trim();
  if (!supabaseUrl || !serviceKey) {
    return json({ errorMessage: "missing supabase env" }, 500);
  }

  const sb = createClient(supabaseUrl, serviceKey, {
    auth: { persistSession: false, autoRefreshToken: false },
  });

  const since = new Date(Date.now() - days * 24 * 60 * 60 * 1000).toISOString();

  const { data: events, error } = await sb
    .from("app_qa_search_events")
    .select(
      "id,created_at,search_mode,query_text,session_id,user_id,comment_hit_count,chunk_hit_count,answer_comment_count,answer_chunk_count"
    )
    .gte("created_at", since)
    .order("created_at", { ascending: false })
    .limit(2000);

  if (error) {
    return json({ errorMessage: error.message }, 500);
  }

  const rows = events || [];
  let normal = 0;
  let semantic = 0;
  const byDay: Record<string, { normal: number; semantic: number }> = {};
  const queryCounts: Record<string, { count: number; semantic: number; normal: number }> = {};

  for (const row of rows) {
    const mode = asString(row.search_mode);
    if (mode === "semantic") semantic += 1;
    else if (mode === "normal") normal += 1;

    const day = asString(row.created_at).slice(0, 10) || "unknown";
    if (!byDay[day]) byDay[day] = { normal: 0, semantic: 0 };
    if (mode === "semantic") byDay[day].semantic += 1;
    else if (mode === "normal") byDay[day].normal += 1;

    const q = asString(row.query_text).trim().replace(/\s+/g, " ").slice(0, 120);
    if (q) {
      if (!queryCounts[q]) queryCounts[q] = { count: 0, semantic: 0, normal: 0 };
      queryCounts[q].count += 1;
      if (mode === "semantic") queryCounts[q].semantic += 1;
      else queryCounts[q].normal += 1;
    }
  }

  const total = normal + semantic;
  const daily = Object.keys(byDay)
    .sort()
    .map((day) => ({
      day,
      normal: byDay[day].normal,
      semantic: byDay[day].semantic,
      total: byDay[day].normal + byDay[day].semantic,
    }));

  const topQueries = Object.entries(queryCounts)
    .map(([query, v]) => ({ query, ...v }))
    .sort((a, b) => b.count - a.count)
    .slice(0, 30);

  const recent = rows.slice(0, 40).map((row) => ({
    id: row.id,
    created_at: row.created_at,
    search_mode: row.search_mode,
    query_text: asString(row.query_text).slice(0, 200),
    comment_hit_count: row.comment_hit_count,
    chunk_hit_count: row.chunk_hit_count,
    answer_comment_count: row.answer_comment_count,
    session_id: row.session_id,
  }));

  return json({
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
    daily,
    top_queries: topQueries,
    recent_events: recent,
  });
});
