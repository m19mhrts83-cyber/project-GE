/**
 * AI社員の段階（設計中 → 運用確認 → 運用）の週次見直し（/review「AI社員の段階」）。
 *
 * 提案を作るのは土曜 9:00 の scripts/jarvis_agent_stage_review.py（週次稼働の履歴と判断ログから・AI なし）→ sync_meta.agent_stage_review。
 * 松野さんが 上げる／見送る／来週また＋理由 を押すと owner_decisions（surface=agent_stage）に残り、
 * 採用分だけ 9:30 の 314 点検が agents_registry.yaml に反映する。物差しは config/agent_stage_review.yaml。
 */
import { createServiceClient } from "@/lib/supabase/admin";

export type Stage = "設計中" | "運用確認" | "運用";

export type StageProposal = {
  key: string;
  id: string;
  name: string;
  from: Stage;
  to: Stage;
  kind: "up" | "down";
  reasons: string[];
  blockers: string[];
  weeks: { day: string; signal: string; why: string }[];
  decisions: { n: number; take: number; ng: number };
  last_decision?: { action: string; at: string; note?: string | null };
};

export type StageReview = {
  generated_at: string;
  week: string;
  counts: Record<Stage, number>;
  proposals: StageProposal[];
  watch: StageProposal[];
  errors: string[];
};

export type StageVerdict = "adopt" | "skip" | "defer";

export const VERDICT_LABEL: Record<StageVerdict, string> = {
  adopt: "上げる",
  skip: "見送る",
  defer: "来週また",
};

export function verdictLabel(v: string, p: Pick<StageProposal, "kind" | "to">): string {
  if (v === "adopt") return p.kind === "down" ? `${p.to}に戻す` : `${p.to}に上げる`;
  return VERDICT_LABEL[v as StageVerdict] || v;
}

export function parseStageReview(raw: unknown): StageReview | null {
  if (!raw) return null;
  try {
    const v = typeof raw === "string" ? JSON.parse(raw) : raw;
    if (!v || !Array.isArray(v.proposals)) return null;
    return { watch: [], errors: [], ...v } as StageReview;
  } catch {
    return null;
  }
}

/** 今週の提案に押した判断（提案キー → 最新の判断） */
export type StageDecided = Record<string, { action: string; note: string | null; at: string }>;

export async function loadStageReview(): Promise<{ review: StageReview | null; decided: StageDecided }> {
  const sb = createServiceClient();
  if (!sb) return { review: null, decided: {} };
  const meta = await sb.from("sync_meta").select("value").eq("key", "agent_stage_review").maybeSingle();
  const review = parseStageReview(meta.data?.value);
  const decided: StageDecided = {};
  if (review) {
    const rows = await sb
      .from("owner_decisions")
      .select("decided_at,action,note,payload")
      .eq("surface", "agent_stage")
      .gte("decided_at", review.generated_at)
      .order("decided_at", { ascending: false })
      .limit(200);
    for (const r of (rows.data || []) as { decided_at: string; action: string; note: string | null; payload: Record<string, unknown> }[]) {
      const k = String(r.payload?.key || "");
      if (k && !decided[k]) decided[k] = { action: r.action, note: r.note, at: r.decided_at };
    }
  }
  return { review, decided };
}
