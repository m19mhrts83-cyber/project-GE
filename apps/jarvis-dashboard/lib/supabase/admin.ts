import { createClient, type SupabaseClient } from "@supabase/supabase-js";

/** Service Role クライアント（Shortcuts ingest 等。ブラウザに出さない） */
export function createServiceClient(): SupabaseClient | null {
  const url = (
    process.env.JARVIS_SUPABASE_URL ||
    process.env.NEXT_PUBLIC_SUPABASE_URL ||
    ""
  ).trim();
  const key = (
    process.env.JARVIS_SUPABASE_SERVICE_ROLE_KEY ||
    process.env.JARVIS_SUPABASE_SECRET_KEY ||
    ""
  ).trim();
  if (!url || !key) return null;
  return createClient(url, key, {
    auth: { persistSession: false, autoRefreshToken: false },
  });
}
