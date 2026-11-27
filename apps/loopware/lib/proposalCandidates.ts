/**
 * 312「提案を仕分ける」の候補を読む（サーバ専用）。/api/misses と /api/counts が同じものを使う。
 * 拾い漏れスキャンが sync_meta.loopware_312_candidates に置いた候補を、同じ中身でまとめ、前に決めたものを外す。
 */
import type { SupabaseClient } from "@supabase/supabase-js";
import { dropDecided, mergeCandidates, topicTextsOf, type MissCandidate, type RawCandidate } from "@/lib/proposalDedupe";

export type ProposalLoad = {
  at?: string;
  candidates: MissCandidate[];
  /** 前に採る／見送るを決めたので出さなかった件数 */
  excluded: number;
  /** 同じ中身をまとめて減った件数 */
  mergedAway: number;
};

/** 前の判断（topic_text → 最新の choice）。読めなければ null（外さずに出す） */
async function pastChoices(sb: SupabaseClient, texts: string[]): Promise<Map<string, string> | null> {
  const out = new Map<string, string>();
  if (!texts.length) return out;
  const { data: topics, error } = await sb
    .from("task_loop_topics")
    .select("id,topic_text")
    .eq("agent_id", "312")
    .in("topic_text", texts.slice(0, 200));
  if (error) return null;
  const textOf = new Map<string, string>();
  for (const t of (topics || []) as { id: string; topic_text: string }[]) textOf.set(t.id, t.topic_text);
  if (!textOf.size) return out;
  const { data: ds, error: dErr } = await sb
    .from("task_loop_decisions")
    .select("topic_id,choice")
    .in("topic_id", [...textOf.keys()]);
  if (dErr) return null;
  for (const d of (ds || []) as { topic_id: string; choice: string }[]) {
    const tx = textOf.get(d.topic_id);
    // 同じ本文の topic が複数あれば、採る・見送るを優先（一度でも決めたら出さない）
    if (tx && (out.get(tx) === undefined || out.get(tx) === "hold")) out.set(tx, d.choice);
  }
  return out;
}

export async function loadProposalCandidates(sb: SupabaseClient, raw?: { at?: string; candidates?: RawCandidate[] } | null): Promise<ProposalLoad | null> {
  let j = raw;
  if (j === undefined) {
    const { data, error } = await sb.from("sync_meta").select("value").eq("key", "loopware_312_candidates").maybeSingle();
    if (error) throw new Error(error.message);
    const v = data?.value;
    j = (typeof v === "string" ? JSON.parse(v) : v) as typeof j;
  }
  if (!j || !Array.isArray(j.candidates)) return null;
  const merged = mergeCandidates(j.candidates);
  const past = await pastChoices(sb, topicTextsOf(merged));
  const { candidates, excluded } = past ? dropDecided(merged, past) : dropDecided(merged, new Map());
  return { at: j.at, candidates, excluded, mergedAway: j.candidates.length - merged.length };
}
