/** 送り手ごとの「次回から」の読み書き（サーバ専用）。純粋な部品は senderPolicyCore.ts */
import type { SupabaseClient } from "@supabase/supabase-js";
import { POLICY_META_KEY, parsePolicies, withPolicy, type PolicyMap, type SenderPolicy } from "@/lib/senderPolicyCore";

export async function loadPolicies(sb: SupabaseClient): Promise<PolicyMap> {
  try {
    const { data } = await sb.from("sync_meta").select("value").eq("key", POLICY_META_KEY).maybeSingle();
    return parsePolicies(data?.value);
  } catch {
    return {}; // 読めなくてもカードは出す
  }
}

export async function savePolicy(sb: SupabaseClient, from: string, policy: SenderPolicy): Promise<boolean> {
  const at = new Date().toISOString();
  const next = withPolicy(await loadPolicies(sb), from, policy, at);
  const { error } = await sb
    .from("sync_meta")
    .upsert({ key: POLICY_META_KEY, value: JSON.stringify({ entries: next }), updated_at: at }, { onConflict: "key" });
  return !error;
}
