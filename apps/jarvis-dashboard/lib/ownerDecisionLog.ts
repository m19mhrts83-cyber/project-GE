/**
 * 松野さんの判断ログ（owner_decisions）への書き込み。
 * triage_items の状態変化は DB トリガーが残すので、ここは後から分かること
 * （Todoist 312 起票／313 完了・延期／S9 採用・見送り／理由・ルール確認・ダッシュボードの判断）用。
 *
 * 形は契約 v1（lib/decisionContract.ts）に揃える:
 *   入口は slack / loopware / dashboard / kurashift / script の5つに寄せ（細かい名前は payload.source_detail）、
 *   payload.v・idem_key・outcome を付け、同じ判断の二重記録を防ぐ。
 * 契約に合わない古い形でも行は捨てない（従来どおり入れて警告だけ出す）。
 * 失敗しても本線は止めない（console.warn のみ）。
 * 週1回 314 業務品質監査係が scripts/jarvis_owner_decisions_weekly.py で読む。
 */
import { createServiceClient } from "@/lib/supabase/admin";
import { normalizeDecision, type DecisionInput } from "@/lib/decisionContract";

export type OwnerDecision = {
  surface: string;
  action: string;
  source?: string;
  employee?: string;
  targetType: string;
  targetId: string;
  subject?: string | null;
  aiProposal?: string | null;
  finalText?: string | null;
  note?: string | null;
  partner?: string | null;
  /** 判断ごとに1つ。再送・二度押しを1行にまとめる */
  idemKey?: string | null;
  reasonTags?: string[];
  appliedRules?: string[];
  timing?: DecisionInput["timing"];
  payload?: Record<string, unknown>;
};

export async function logOwnerDecision(d: OwnerDecision): Promise<void> {
  try {
    const sb = createServiceClient();
    if (!sb) return;
    const n = normalizeDecision({ ...d, source: d.source || "dashboard" });
    if (n.ok) {
      const { data: dup } = await sb
        .from("owner_decisions")
        .select("id")
        .eq("payload->>idem_key", n.idemKey)
        .limit(1)
        .maybeSingle();
      if (dup) return;
      const { error } = await sb.from("owner_decisions").insert(n.row);
      if (error && error.code !== "23505") console.warn(`owner_decisions soft-fail: ${error.message}`);
      return;
    }
    console.warn(`owner_decisions contract: ${n.error}（従来の形で記録）`);
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
      payload: { ...(d.payload || {}), contract_error: n.error },
    });
    if (error) console.warn(`owner_decisions soft-fail: ${error.message}`);
  } catch (e) {
    console.warn(
      `owner_decisions soft-fail: ${e instanceof Error ? e.message : String(e)}`,
    );
  }
}
