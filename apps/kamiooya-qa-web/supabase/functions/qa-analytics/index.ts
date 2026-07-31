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
      "id,created_at,search_mode,query_text,session_id,user_id,comment_hit_count,chunk_hit_count,answer_comment_count,answer_chunk_count,result_status,error_message"
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
  let failed = 0;
  let disabled = 0;
  let billableNormal = 0;
  let billableSemantic = 0;
  const byDay: Record<string, { normal: number; semantic: number }> = {};
  const queryCounts: Record<string, { count: number; semantic: number; normal: number }> = {};

  for (const row of rows) {
    const mode = asString(row.search_mode);
    const status = asString(row.result_status) || "ok";
    if (status !== "ok") failed += 1;
    if (status === "disabled") disabled += 1;
    if (mode === "semantic") semantic += 1;
    else if (mode === "normal") normal += 1;
    if (status === "ok") {
      if (mode === "semantic") billableSemantic += 1;
      else if (mode === "normal") billableNormal += 1;
    }

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
    result_status: asString(row.result_status) || "ok",
    error_message: asString(row.error_message) || null,
  }));

  // Gemini 想定課金（試算）。単価は ランニングコスト試算_会員規模.md 準拠。
  const UNIT_NORMAL_LOW = 0.02;
  const UNIT_NORMAL_HIGH = 0.04;
  const UNIT_SEMANTIC_LOW = 0.01;
  const UNIT_SEMANTIC_HIGH = 0.025;
  const USD_PER_JPY = 150;
  const usdLow = billableNormal * UNIT_NORMAL_LOW + billableSemantic * UNIT_SEMANTIC_LOW;
  const usdHigh = billableNormal * UNIT_NORMAL_HIGH + billableSemantic * UNIT_SEMANTIC_HIGH;
  const roundUsd = (n: number) => Math.round(n * 100) / 100;
  const geminiEstimate = {
    billable_normal: billableNormal,
    billable_semantic: billableSemantic,
    billable_total: billableNormal + billableSemantic,
    usd_low: roundUsd(usdLow),
    usd_high: roundUsd(usdHigh),
    jpy_low: Math.round(usdLow * USD_PER_JPY),
    jpy_high: Math.round(usdHigh * USD_PER_JPY),
    usd_per_jpy: USD_PER_JPY,
    unit_usd: {
      normal_low: UNIT_NORMAL_LOW,
      normal_high: UNIT_NORMAL_HIGH,
      semantic_low: UNIT_SEMANTIC_LOW,
      semantic_high: UNIT_SEMANTIC_HIGH,
    },
    note: "想定レンジ。Google請求額そのものではありません。",
  };

  return json({
    ok: true,
    range_days: days,
    since,
    totals: {
      total,
      normal,
      semantic,
      failed,
      disabled,
      semantic_ratio: total > 0 ? Number((semantic / total).toFixed(4)) : 0,
      normal_ratio: total > 0 ? Number((normal / total).toFixed(4)) : 0,
    },
    gemini_estimate: geminiEstimate,
    daily,
    top_queries: topQueries,
    recent_events: recent,
  });
});
