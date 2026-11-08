/**
 * 見落とし（/misses?surface=triage）。仕分けが「出さない」にしたもののうち、
 * 本当は要対応だったものを拾い直す。判断は surface=triage_miss で残す。
 *   - 送り手の自動見送り（同じ送り手を2回見送った → 以後自動で見送り）
 *   - Slack に出なかったまま 2 日たった未判断
 */
import type { SupabaseClient } from "@supabase/supabase-js";
import { toCard, type DeskCard, type TriageRow } from "@/lib/deskCore";

export type MissCard = DeskCard & { why: "auto_skip" | "not_surfaced" };

const COLS =
  "id,status,subject,partner,from_email,lane,kind,summary,draft_text,original_body,received_at,priority,payload,updated_at";

function obj(x: unknown): Record<string, unknown> {
  return x && typeof x === "object" && !Array.isArray(x) ? (x as Record<string, unknown>) : {};
}

export async function loadMisses(sb: SupabaseClient, limit = 20): Promise<MissCard[]> {
  const since = new Date(Date.now() - 14 * 86400_000).toISOString();
  const twoDays = Date.now() - 2 * 86400_000;
  const [auto, pend] = await Promise.all([
    sb.from("triage_items").select(COLS).eq("status", "skipped").gte("updated_at", since).order("updated_at", { ascending: false }).limit(100),
    sb.from("triage_items").select(COLS).eq("status", "pending").in("lane", ["partner", "general"]).gte("received_at", since).order("received_at", { ascending: false }).limit(200),
  ]);
  const out: MissCard[] = [];
  for (const r of (auto.data || []) as TriageRow[]) {
    const pl = obj(r.payload);
    if (!pl.mail_skip_mute_auto || pl.loopware_miss_judged_at) continue;
    out.push({ ...toCard(r), why: "auto_skip" });
  }
  for (const r of (pend.data || []) as TriageRow[]) {
    const pl = obj(r.payload);
    if (pl.slack_ma_posted_at || pl.loopware_miss_judged_at || pl.loopware_hesitated_at) continue;
    const t = Date.parse(String(r.received_at || ""));
    if (!Number.isFinite(t) || t > twoDays) continue;
    out.push({ ...toCard(r), why: "not_surfaced" });
  }
  return out.slice(0, limit);
}

/** 判断を案件に印（もう一度出さない）。見落としなら要対応に戻し、デスクの先頭へ */
export async function markMiss(sb: SupabaseClient, id: string, isMiss: boolean): Promise<{ restored: boolean }> {
  const { data } = await sb.from("triage_items").select("status,payload").eq("id", id).maybeSingle();
  if (!data) return { restored: false };
  const pl = { ...obj(data.payload) };
  const now = new Date().toISOString();
  pl.loopware_miss_judged_at = now;
  pl.loopware_miss = isMiss;
  const patch: Record<string, unknown> = { payload: pl, updated_at: now };
  let restored = false;
  if (isMiss && data.status === "skipped") {
    patch.status = "pending";
    pl.loopware_restored_at = now;
    restored = true;
  }
  if (isMiss) {
    // デスクで先頭に来るよう、Slack に出したものと同じ扱いの印と高い点数
    pl.slack_ma_digest = { ...obj(pl.slack_ma_digest), score: 999, summary: obj(pl.slack_ma_digest).summary || "見落としから戻した" };
    pl.slack_ma_posted_at = pl.slack_ma_posted_at || now;
  }
  await sb.from("triage_items").update(patch).eq("id", id);
  return { restored };
}
