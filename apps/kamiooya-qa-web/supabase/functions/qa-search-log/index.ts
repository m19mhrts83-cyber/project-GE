// Phase 13: log normal/semantic search events from the Raimo frontend.
// Auth: X-Semantic-Shared-Secret. Deploy with --no-verify-jwt.

import { createClient } from "https://esm.sh/@supabase/supabase-js@2.49.1";

type LogBody = {
  search_mode?: string;
  query?: string;
  query_text?: string;
  session_id?: string;
  user_id?: string;
  comment_hit_count?: number;
  chunk_hit_count?: number;
  used_sources?: unknown;
  meta?: Record<string, unknown>;
  secret?: string;
};

function corsHeaders(): HeadersInit {
  return {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Headers":
      "authorization, x-client-info, apikey, content-type, x-semantic-shared-secret",
    "Access-Control-Allow-Methods": "POST, OPTIONS",
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

function isAuthorized(req: Request, body: LogBody | null): boolean {
  const expected = (Deno.env.get("SEMANTIC_SEARCH_SHARED_SECRET") || "").trim();
  if (!expected) return true;
  const headerSecret = (req.headers.get("x-semantic-shared-secret") || "").trim();
  const bodySecret = asString(body?.secret).trim();
  return headerSecret === expected || bodySecret === expected;
}

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") {
    return new Response("ok", { headers: corsHeaders() });
  }
  if (req.method !== "POST") {
    return json({ errorMessage: "method_not_allowed" }, 405);
  }

  const body = (await req.json().catch(() => null)) as LogBody | null;
  if (!isAuthorized(req, body)) {
    return json({ errorMessage: "forbidden" }, 403);
  }

  const mode = asString(body?.search_mode).trim();
  if (mode !== "normal" && mode !== "semantic") {
    return json({ errorMessage: "search_mode must be normal or semantic" }, 400);
  }

  const queryText = asString(body?.query_text || body?.query).trim().slice(0, 2000);
  if (!queryText) {
    return json({ errorMessage: "query_text required" }, 400);
  }

  const supabaseUrl = (Deno.env.get("SUPABASE_URL") || "").trim();
  const serviceKey = (Deno.env.get("SUPABASE_SERVICE_ROLE_KEY") || "").trim();
  if (!supabaseUrl || !serviceKey) {
    return json({ errorMessage: "missing supabase env" }, 500);
  }

  const sb = createClient(supabaseUrl, serviceKey, {
    auth: { persistSession: false, autoRefreshToken: false },
  });

  const { error } = await sb.from("app_qa_search_events").insert({
    search_mode: mode,
    query_text: queryText,
    session_id: asString(body?.session_id) || null,
    user_id: asString(body?.user_id) || null,
    comment_hit_count:
      body?.comment_hit_count == null ? null : Number(body.comment_hit_count),
    chunk_hit_count: body?.chunk_hit_count == null ? null : Number(body.chunk_hit_count),
    used_sources: body?.used_sources ?? null,
    meta: body?.meta && typeof body.meta === "object" ? body.meta : {},
  });

  if (error) {
    return json({ errorMessage: error.message }, 500);
  }
  return json({ ok: true });
});
