// Phase 13: Q&A search analytics overview for operators.
// Auth: X-Semantic-Shared-Secret. Deploy with --no-verify-jwt.

import { createClient } from "https://esm.sh/@supabase/supabase-js@2.49.1";

type Body = {
  days?: number;
  /** 実測期間の開始日（JST, YYYY-MM-DD）。指定時は days より優先 */
  since?: string;
  /** 実測期間の終了日（JST, YYYY-MM-DD, この日を含む） */
  until?: string;
  secret?: string;
};

type WeeklyRow = {
  week_start_jst: string;
  search_mode: string;
  ok_count: number;
  failed_count: number;
  unique_users: number;
  unique_sessions: number;
  metered_count: number;
  prompt_tokens: number;
  output_tokens: number;
  thought_tokens: number;
};

/** JST の日付文字列 → その日 0:00 JST の ISO。不正なら null */
function jstDateToIso(value: unknown, addDays = 0): string | null {
  const s = typeof value === "string" ? value.trim() : "";
  if (!/^\d{4}-\d{2}-\d{2}$/.test(s)) return null;
  const t = Date.parse(`${s}T00:00:00+09:00`);
  if (!Number.isFinite(t)) return null;
  return new Date(t + addDays * 24 * 60 * 60 * 1000).toISOString();
}

function envNumber(name: string, fallback: number): number {
  const v = Number((Deno.env.get(name) || "").trim());
  return Number.isFinite(v) && v > 0 ? v : fallback;
}

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

  const params = new URL(req.url).searchParams;
  const daysRaw = Number(body?.days ?? params.get("days") ?? 14);
  const days = Math.max(1, Math.min(365, Number.isFinite(daysRaw) ? daysRaw : 14));
  const sinceParam = body?.since ?? params.get("since");
  const untilParam = body?.until ?? params.get("until");

  const supabaseUrl = (Deno.env.get("SUPABASE_URL") || "").trim();
  const serviceKey = (Deno.env.get("SUPABASE_SERVICE_ROLE_KEY") || "").trim();
  if (!supabaseUrl || !serviceKey) {
    return json({ errorMessage: "missing supabase env" }, 500);
  }

  const sb = createClient(supabaseUrl, serviceKey, {
    auth: { persistSession: false, autoRefreshToken: false },
  });

  const since =
    jstDateToIso(sinceParam) || new Date(Date.now() - days * 24 * 60 * 60 * 1000).toISOString();
  const until = jstDateToIso(untilParam, 1);
  const rangeDays = Math.max(
    1,
    Math.round(((until ? Date.parse(until) : Date.now()) - Date.parse(since)) / 86400000)
  );

  const { data: events, error } = await sb
    .from("app_qa_search_events")
    .select(
      "id,created_at,search_mode,query_text,session_id,user_id,comment_hit_count,chunk_hit_count,answer_comment_count,answer_chunk_count,result_status,error_message"
    )
    .gte("created_at", since)
    .lt("created_at", until || "9999-12-31T00:00:00Z")
    .order("created_at", { ascending: false })
    .limit(2000);

  if (error) {
    return json({ errorMessage: error.message }, 500);
  }

  // 実測用の週次集計（件数上限なし）。migration 未適用なら null で返し、画面側で案内する
  const weeklyRes = await sb.rpc("qa_usage_weekly", { p_since: since, p_until: until });
  const usersRes = await sb.rpc("qa_usage_period_users", { p_since: since, p_until: until });
  const weeklyRows: WeeklyRow[] | null = weeklyRes.error ? null : (weeklyRes.data as WeeklyRow[]) || [];

  const rows = events || [];

  // 「より詳しく調べる」(deep) は記録上は意味検索(semantic)なので、回答ジョブ(qa_answer_jobs.mode='deep')と
  // 同じチャット・同じ質問・10分以内で突き合わせて見分ける。読めなければ今までどおり意味検索に数える。2026-11-11
  const DEEP_WINDOW_MS = 10 * 60 * 1000;
  const deepJobs: Record<string, number[]> = {};
  try {
    const { data: jobs } = await sb
      .from("qa_answer_jobs")
      .select("chat_id,query,created_at")
      .eq("mode", "deep")
      .gte("created_at", new Date(Date.parse(since) - DEEP_WINDOW_MS).toISOString())
      .lt("created_at", until || "9999-12-31T00:00:00Z")
      .limit(5000);
    for (const j of jobs || []) {
      const k = asString(j.chat_id) + "\u0000" + asString(j.query).slice(0, 2000);
      (deepJobs[k] ||= []).push(Date.parse(asString(j.created_at)));
    }
  } catch {
    /* 突き合わせできなくても集計は出す */
  }
  const isDeep = (row: Record<string, unknown>): boolean => {
    if (asString(row.search_mode) !== "semantic") return false;
    const times = deepJobs[asString(row.session_id) + "\u0000" + asString(row.query_text)];
    if (!times) return false;
    const t = Date.parse(asString(row.created_at));
    return times.some((jt) => t >= jt && t - jt <= DEEP_WINDOW_MS);
  };
  const modeOf = (row: Record<string, unknown>): string => (isDeep(row) ? "deep" : asString(row.search_mode));

  let normal = 0;
  let semantic = 0;
  let deep = 0;
  let deepOk = 0;
  let failed = 0;
  let disabled = 0;
  let billableNormal = 0;
  let billableSemantic = 0;
  const byDay: Record<string, { normal: number; semantic: number; deep: number }> = {};
  const queryCounts: Record<string, { count: number; semantic: number; normal: number; deep: number }> = {};

  for (const row of rows) {
    const mode = modeOf(row);
    const status = asString(row.result_status) || "ok";
    if (status !== "ok") failed += 1;
    if (status === "disabled") disabled += 1;
    if (mode === "semantic") semantic += 1;
    else if (mode === "deep") deep += 1;
    else if (mode === "normal") normal += 1;
    if (status === "ok") {
      // 費用の試算・実測では、より詳しくも意味検索（同じ Gemini の実トークン）として数える
      if (mode === "semantic" || mode === "deep") billableSemantic += 1;
      else if (mode === "normal") billableNormal += 1;
      if (mode === "deep") deepOk += 1;
    }

    const day = asString(row.created_at).slice(0, 10) || "unknown";
    if (!byDay[day]) byDay[day] = { normal: 0, semantic: 0, deep: 0 };
    if (mode === "semantic") byDay[day].semantic += 1;
    else if (mode === "deep") byDay[day].deep += 1;
    else if (mode === "normal") byDay[day].normal += 1;

    const q = asString(row.query_text).trim().replace(/\s+/g, " ").slice(0, 120);
    if (q) {
      if (!queryCounts[q]) queryCounts[q] = { count: 0, semantic: 0, normal: 0, deep: 0 };
      queryCounts[q].count += 1;
      if (mode === "semantic") queryCounts[q].semantic += 1;
      else if (mode === "deep") queryCounts[q].deep += 1;
      else queryCounts[q].normal += 1;
    }
  }

  if (weeklyRows) {
    // 2,000件の取得上限を超えても正しい件数になるよう、件数は週次集計から出す
    normal = 0;
    semantic = 0;
    failed = 0;
    billableNormal = 0;
    billableSemantic = 0;
    for (const w of weeklyRows) {
      const all = Number(w.ok_count) + Number(w.failed_count);
      failed += Number(w.failed_count);
      if (w.search_mode === "semantic") {
        semantic += all;
        billableSemantic += Number(w.ok_count);
      } else if (w.search_mode === "normal") {
        normal += all;
        billableNormal += Number(w.ok_count);
      }
    }
  }

  // 週次集計の意味検索には、より詳しくも入っているので分けて出す（費用の billableSemantic はそのまま）
  if (weeklyRows) semantic = Math.max(0, semantic - deep);
  const total = normal + semantic + deep;
  const daily = Object.keys(byDay)
    .sort()
    .map((day) => ({
      day,
      normal: byDay[day].normal,
      semantic: byDay[day].semantic,
      deep: byDay[day].deep,
      total: byDay[day].normal + byDay[day].semantic + byDay[day].deep,
    }));

  const topQueries = Object.entries(queryCounts)
    .map(([query, v]) => ({ query, ...v }))
    .sort((a, b) => b.count - a.count)
    .slice(0, 30);

  const recent = rows.slice(0, 40).map((row) => ({
    id: row.id,
    created_at: row.created_at,
    search_mode: modeOf(row),
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

  // 実測（意味検索の要約は実トークン × 公開単価、通常検索は Raimo 側のため件数 × 単価目安）
  const PRICE_IN = envNumber("GEMINI_PRICE_INPUT_USD_PER_M", 0.5);
  const PRICE_OUT = envNumber("GEMINI_PRICE_OUTPUT_USD_PER_M", 3.0);
  const JPY = envNumber("USD_JPY_RATE", USD_PER_JPY);
  const tokenUsd = (p: number, o: number, t: number) => (p * PRICE_IN + (o + t) * PRICE_OUT) / 1e6;
  let metering: Record<string, unknown> | null = null;
  if (weeklyRows) {
    const weeks: Record<string, Record<string, number | string>> = {};
    let pTok = 0, oTok = 0, tTok = 0, meteredSemantic = 0;
    for (const w of weeklyRows) {
      const key = String(w.week_start_jst);
      if (!weeks[key]) {
        weeks[key] = {
          week_start_jst: key, normal_ok: 0, semantic_ok: 0, failed: 0,
          users_max_mode: 0, semantic_metered: 0, prompt_tokens: 0, output_tokens: 0, thought_tokens: 0,
        };
      }
      const r = weeks[key] as Record<string, number>;
      if (w.search_mode === "normal") r.normal_ok += Number(w.ok_count);
      if (w.search_mode === "semantic") r.semantic_ok += Number(w.ok_count);
      r.failed += Number(w.failed_count);
      r.users_max_mode = Math.max(r.users_max_mode, Number(w.unique_users));
      if (w.search_mode === "semantic") {
        r.semantic_metered += Number(w.metered_count);
        r.prompt_tokens += Number(w.prompt_tokens);
        r.output_tokens += Number(w.output_tokens);
        r.thought_tokens += Number(w.thought_tokens);
        meteredSemantic += Number(w.metered_count);
        pTok += Number(w.prompt_tokens);
        oTok += Number(w.output_tokens);
        tTok += Number(w.thought_tokens);
      }
    }
    const perSemanticUsd = meteredSemantic > 0 ? tokenUsd(pTok, oTok, tTok) / meteredSemantic : null;
    const round4 = (n: number) => Math.round(n * 10000) / 10000;
    const weekly = Object.values(weeks)
      .sort((a, b) => String(a.week_start_jst).localeCompare(String(b.week_start_jst)))
      .map((r) => {
        const x = r as Record<string, number>;
        const semMeasured = tokenUsd(x.prompt_tokens, x.output_tokens, x.thought_tokens);
        // トークン未記録の意味検索（改修前の分など）は、記録済み分の平均単価で補う
        const semUnmetered = Math.max(0, x.semantic_ok - x.semantic_metered);
        const semUsd = semMeasured + (perSemanticUsd ?? UNIT_SEMANTIC_HIGH) * semUnmetered;
        const normLow = x.normal_ok * UNIT_NORMAL_LOW;
        const normHigh = x.normal_ok * UNIT_NORMAL_HIGH;
        return {
          week_start_jst: r.week_start_jst,
          questions: x.normal_ok + x.semantic_ok,
          normal_ok: x.normal_ok,
          semantic_ok: x.semantic_ok,
          failed: x.failed,
          users: x.users_max_mode,
          semantic_metered: x.semantic_metered,
          prompt_tokens: x.prompt_tokens,
          output_tokens: x.output_tokens + x.thought_tokens,
          semantic_usd: round4(semUsd),
          normal_usd_low: round4(normLow),
          normal_usd_high: round4(normHigh),
          total_jpy_low: Math.round((semUsd + normLow) * JPY),
          total_jpy_high: Math.round((semUsd + normHigh) * JPY),
        };
      });
    const semUsdAll = weekly.reduce((a, w) => a + w.semantic_usd, 0);
    const normLowAll = billableNormal * UNIT_NORMAL_LOW;
    const normHighAll = billableNormal * UNIT_NORMAL_HIGH;
    const questionsAll = billableNormal + billableSemantic;
    metering = {
      period_users: usersRes.error ? null : Number(usersRes.data) || 0,
      questions: questionsAll,
      semantic_metered: meteredSemantic,
      prompt_tokens: pTok,
      output_tokens: oTok + tTok,
      semantic_usd_per_question: perSemanticUsd == null ? null : round4(perSemanticUsd),
      semantic_usd: round4(semUsdAll),
      normal_usd_low: round4(normLowAll),
      normal_usd_high: round4(normHighAll),
      total_jpy_low: Math.round((semUsdAll + normLowAll) * JPY),
      total_jpy_high: Math.round((semUsdAll + normHighAll) * JPY),
      jpy_per_question_low: questionsAll > 0 ? Math.round(((semUsdAll + normLowAll) * JPY / questionsAll) * 100) / 100 : null,
      jpy_per_question_high: questionsAll > 0 ? Math.round(((semUsdAll + normHighAll) * JPY / questionsAll) * 100) / 100 : null,
      price_usd_per_m: { input: PRICE_IN, output: PRICE_OUT },
      usd_jpy: JPY,
      weekly,
      note:
        "意味検索は実トークン×公開単価、通常検索はRaimo側でGeminiを呼ぶため件数×単価目安。Google請求額（AI Studio）と突き合わせて確認してください。",
    };
  }

  return json({
    ok: true,
    range_days: sinceParam ? rangeDays : days,
    since,
    until,
    totals: {
      total,
      normal,
      semantic,
      deep,
      deep_ok: deepOk,
      failed,
      disabled,
      semantic_ratio: total > 0 ? Number((semantic / total).toFixed(4)) : 0,
      deep_ratio: total > 0 ? Number((deep / total).toFixed(4)) : 0,
      normal_ratio: total > 0 ? Number((normal / total).toFixed(4)) : 0,
    },
    gemini_estimate: geminiEstimate,
    metering,
    metering_error: weeklyRes.error ? weeklyRes.error.message : null,
    daily,
    top_queries: topQueries,
    recent_events: recent,
  });
});
