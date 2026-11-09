import type { SupabaseClient } from "@supabase/supabase-js";
import type { SeedTopic } from "@/lib/seed312";

/**
 * 312 collect（scripts/jarvis_todoist_312_collect.py）が入れた本物のお題。
 * まだ決めていないもの（status=open）を新しい順に返す。見本（seed）は含めない。
 */
export async function loadOpenTopics312(sb: SupabaseClient, limit = 20): Promise<SeedTopic[]> {
  const { data: topics, error } = await sb
    .from("task_loop_topics")
    .select("id,topic_text,source_ref,source_kind,created_at")
    .eq("agent_id", "312")
    .eq("status", "open")
    .neq("source_kind", "seed")
    .order("created_at", { ascending: false })
    .limit(limit);
  if (error) throw new Error(error.message);
  const rows = (topics || []) as { id: string; topic_text: string; source_ref: string | null }[];
  if (!rows.length) return [];
  const { data: props, error: pErr } = await sb
    .from("task_loop_proposals")
    .select("topic_id,proposal_index,label,body,is_starred")
    .in("topic_id", rows.map((r) => r.id));
  if (pErr) throw new Error(pErr.message);
  const byTopic = new Map<string, { index: number; label: string; body: string; starred: boolean }[]>();
  for (const p of (props || []) as { topic_id: string; proposal_index: number; label: string; body: string; is_starred: boolean }[]) {
    const list = byTopic.get(p.topic_id) || [];
    list.push({ index: p.proposal_index, label: p.label, body: p.body, starred: !!p.is_starred });
    byTopic.set(p.topic_id, list);
  }
  return rows
    .map((r) => {
      const list = (byTopic.get(r.id) || []).sort((a, b) => a.index - b.index);
      return {
        id: r.id,
        dbId: r.id,
        title: titleOf(r.topic_text),
        topicText: r.topic_text,
        sourceRef: r.source_ref || undefined,
        starred: list.find((p) => p.starred)?.index,
        proposals: list.map(({ index, label, body }) => ({ index, label, body })),
      };
    })
    .filter((t) => t.proposals.length > 0);
}

/** 「[Slack #consult 11/2 00:38・依頼] todoistへ追加して。315健全化…」→「315健全化…」（タブ用の短い名前） */
export function titleOf(text: string): string {
  const body = text.replace(/^\[[^\]]*\]\s*/, "").split("\n")[0];
  const t = body.replace(/^(todoist(へ|に)?(追加し|入れ)て(おいて|ください)?[。、,\s]*|起票して[。、,\s]*)/i, "");
  return t.length > 14 ? `${t.slice(0, 14)}…` : t || "お題";
}
