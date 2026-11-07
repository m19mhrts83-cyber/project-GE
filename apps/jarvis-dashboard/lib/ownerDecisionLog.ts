/**
 * 松野さんの判断ログ（owner_decisions）への書き込み。
 * triage_items の判断は DB トリガーが残すので、ここは triage 以外
 * （Todoist 312 起票／313 完了・延期／S9 採用・見送り）用。
 * 失敗しても本線は止めない（console.warn のみ）。
 * 週1回 314 業務品質監査係が scripts/jarvis_owner_decisions_weekly.py で読む。
 */
import { createServiceClient } from "@/lib/supabase/admin";

export type OwnerDecision = {
  surface: "todoist_312" | "todoist_313" | "s9";
  action: string;
  source?: string;
  employee?: string;
  targetType: string;
  targetId: string;
  subject?: string | null;
  aiProposal?: string | null;
  note?: string | null;
  payload?: Record<string, unknown>;
};

export async function logOwnerDecision(d: OwnerDecision): Promise<void> {
  try {
    const sb = createServiceClient();
    if (!sb) return;
    const { error } = await sb.from("owner_decisions").insert({
      surface: d.surface,
      action: d.action,
      source: d.source || null,
      employee: d.employee || null,
      target_type: d.targetType,
      target_id: d.targetId || "-",
      subject: d.subject ? d.subject.slice(0, 500) : null,
      ai_proposal: d.aiProposal ? d.aiProposal.slice(0, 4000) : null,
      note: d.note || null,
      payload: d.payload || {},
    });
    if (error) console.warn(`owner_decisions soft-fail: ${error.message}`);
  } catch (e) {
    console.warn(
      `owner_decisions soft-fail: ${e instanceof Error ? e.message : String(e)}`,
    );
  }
}
