/**
 * 運営共有 kamiooya-qa（読取専用）。JARVIS_SUPABASE_* とは別。
 */
import { createClient, type SupabaseClient } from "@supabase/supabase-js";

export function kamiooyaAdminOrNull(): SupabaseClient | null {
  const url = (process.env.SUPABASE_URL || "").trim();
  const key = (process.env.SUPABASE_SERVICE_ROLE_KEY || "").trim();
  if (!url || !key) return null;
  return createClient(url, key, {
    auth: { persistSession: false, autoRefreshToken: false },
  });
}
