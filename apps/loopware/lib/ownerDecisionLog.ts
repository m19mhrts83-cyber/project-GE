/**
 * 判断ログ（owner_decisions）への書き込み（サーバ専用）。
 * 契約は lib/decisionContract.ts。失敗しても画面は止めない。
 */
import type { SupabaseClient } from "@supabase/supabase-js";
import { normalizeDecision, type DecisionInput } from "@/lib/decisionContract";

export type LogResult =
  | { ok: true; persisted: true; id: number | null; duplicate: boolean; idemKey: string }
  | { ok: true; persisted: false; reason: string; idemKey?: string }
  | { ok: false; error: string };

export async function writeDecision(sb: SupabaseClient | null, input: DecisionInput): Promise<LogResult> {
  const n = normalizeDecision(input);
  if (!n.ok) return { ok: false, error: n.error };
  if (!sb) return { ok: true, persisted: false, reason: "supabase_unconfigured", idemKey: n.idemKey };
  try {
    // 同じ判断の再送（電波が切れて再送・二度押し）は1行にまとめる
    const { data: dup } = await sb
      .from("owner_decisions")
      .select("id")
      .eq("payload->>idem_key", n.idemKey)
      .limit(1)
      .maybeSingle();
    if (dup) return { ok: true, persisted: true, id: Number(dup.id), duplicate: true, idemKey: n.idemKey };

    const { data, error } = await sb.from("owner_decisions").insert(n.row).select("id").single();
    if (error) {
      // 一意索引（20261108 migration）に当たった＝同時に2回届いた
      if (error.code === "23505") {
        return { ok: true, persisted: true, id: null, duplicate: true, idemKey: n.idemKey };
      }
      console.warn(`owner_decisions soft-fail: ${error.message}`);
      return { ok: true, persisted: false, reason: error.message, idemKey: n.idemKey };
    }
    return { ok: true, persisted: true, id: Number(data?.id ?? 0) || null, duplicate: false, idemKey: n.idemKey };
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e);
    console.warn(`owner_decisions soft-fail: ${msg}`);
    return { ok: true, persisted: false, reason: msg, idemKey: n.idemKey };
  }
}
