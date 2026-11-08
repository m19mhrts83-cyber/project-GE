/**
 * ルール候補（土曜に週次分析が sync_meta.loopware_rule_candidates に置く）と、採用済みルール。
 * 人は loopware で1回押すだけ（採用＝承認）。ルール帳への反映は scripts/jarvis_loopware_apply_rules.py。
 */
import type { SupabaseClient } from "@supabase/supabase-js";

export type RuleCandidate = {
  id: string;
  kind: "hide" | "keep" | "rewrite" | "template" | string;
  employee: string;
  key: string;
  rule_line: string;
  text: string;
  why: string;
  evidence: (number | string)[];
  status: "hypothesis" | "candidate";
  needs_ai?: boolean;
};

export type AdoptedRule = { decisionId: number; ruleId: string | null; employee: string; text: string; at: string; reverted: boolean };

/** 自律度のはしご（設計書）。仮説 → 提案して承認 → 自動＋週次まとめ → 自動＋抜き取り */
export const LADDER = ["仮説", "提案して承認", "自動＋週次まとめ", "自動＋抜き取り"] as const;

export function ladderStep(c: Pick<RuleCandidate, "status">): number {
  return c.status === "hypothesis" ? 0 : 1;
}

export async function loadRules(sb: SupabaseClient): Promise<{ week: string | null; candidates: RuleCandidate[]; adopted: AdoptedRule[]; decided: string[] }> {
  const { data: meta } = await sb.from("sync_meta").select("value").eq("key", "loopware_rule_candidates").maybeSingle();
  let week: string | null = null;
  let candidates: RuleCandidate[] = [];
  try {
    const v = JSON.parse(String(meta?.value || "{}")) as { week?: string; candidates?: RuleCandidate[] };
    week = v.week || null;
    candidates = Array.isArray(v.candidates) ? v.candidates : [];
  } catch {
    /* まだ無い */
  }
  const since = new Date(Date.now() - 60 * 86400_000).toISOString();
  const { data: rows } = await sb
    .from("owner_decisions")
    .select("id,action,target_id,payload,decided_at")
    .eq("surface", "rule_review")
    .gte("decided_at", since)
    .order("decided_at", { ascending: false })
    .limit(200);
  const decided: string[] = [];
  const reverted = new Set<string>();
  const adopted: AdoptedRule[] = [];
  for (const r of rows || []) {
    const pl = (r.payload || {}) as Record<string, unknown>;
    if (r.action === "rule_revert" && pl.rule_id) reverted.add(String(pl.rule_id));
  }
  for (const r of rows || []) {
    const pl = (r.payload || {}) as Record<string, unknown>;
    if (["rule_accept", "rule_once", "rule_reject"].includes(String(r.action))) decided.push(String(r.target_id));
    if (r.action === "rule_accept") {
      const rid = pl.rule_id ? String(pl.rule_id) : null;
      adopted.push({
        decisionId: Number(r.id),
        ruleId: rid,
        employee: String(pl.employee || ""),
        text: String(pl.text || pl.rule_line || ""),
        at: String(r.decided_at),
        reverted: rid ? reverted.has(rid) : false,
      });
    }
  }
  return { week, candidates, adopted: adopted.slice(0, 20), decided };
}
