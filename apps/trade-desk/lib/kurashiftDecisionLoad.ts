/**
 * 判断ログの読み込み（サーバー側）。/decisions・判断メモのヒント・ホームが同じ材料を使う。
 */
import type { SupabaseClient } from "@supabase/supabase-js";
import { dealRows, moneyRows, sortNewest, type DecisionRow } from "./kurashiftDecisionLog";

export async function loadDecisionRows(
  supabase: SupabaseClient,
  days: number
): Promise<DecisionRow[]> {
  const since = new Date(Date.now() - days * 86400_000).toISOString();
  const [{ data: ops }, { data: events }] = await Promise.all([
    supabase
      .from("kurashift_money_ops")
      .select("id, title, kind, amount_jpy, assist_payload, updated_at")
      .gte("updated_at", since)
      .order("updated_at", { ascending: false })
      .limit(200),
    supabase
      .from("kurashift_re_deal_events")
      .select("id, deal_id, event_type, actor, occurred_at, payload")
      .eq("actor", "user")
      .in("event_type", ["review_confirm", "review_pass", "status_change", "note"])
      .gte("occurred_at", since)
      .order("occurred_at", { ascending: false })
      .limit(500),
  ]);

  const dealIds = Array.from(new Set((events ?? []).map((e) => e.deal_id as string)));
  const titles = new Map<string, string>();
  if (dealIds.length) {
    const { data: deals } = await supabase
      .from("kurashift_re_deals")
      .select("id, title")
      .in("id", dealIds.slice(0, 400));
    for (const d of deals ?? []) titles.set(d.id as string, (d.title as string) || "");
  }

  return sortNewest([
    ...moneyRows(ops ?? []).filter((r) => r.at >= since),
    ...dealRows(events ?? [], titles),
  ]);
}
