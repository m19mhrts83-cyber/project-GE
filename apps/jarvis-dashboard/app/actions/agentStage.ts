"use server";

/**
 * 週次レビュー（/review「AI社員の段階」）での段階の判断: 上げる（戻す）／見送る／来週また＋理由。
 * owner_decisions（surface=agent_stage）に残す。中身は画面から受け取らず、最新の提案（sync_meta.agent_stage_review）から取る。
 * 採用分の registry 反映は 9:30 の 314 点検（scripts/jarvis_agent_stage_review.py --apply --commit）。
 */
import { revalidatePath } from "next/cache";
import { createClient } from "@/lib/supabase/server";
import { createServiceClient } from "@/lib/supabase/admin";
import { normalizeDecision } from "@/lib/decisionContract";
import { parseStageReview, type StageVerdict } from "@/lib/agentStageReview";

export type StageJudgeResult = { ok: true; duplicate: boolean } | { ok: false; error: string };

export async function judgeStage(key: string, verdict: StageVerdict, idemKey: string, note?: string): Promise<StageJudgeResult> {
  const auth = await createClient();
  const {
    data: { user },
  } = await auth.auth.getUser();
  if (!user) return { ok: false, error: "ログインが切れています" };
  if (!["adopt", "skip", "defer"].includes(verdict)) return { ok: false, error: "判断の種類が不正です" };
  if (String(idemKey || "").length < 8) return { ok: false, error: "idemKey" };
  const text = String(note || "").trim().slice(0, 2000);

  const sb = createServiceClient();
  if (!sb) return { ok: false, error: "Supabase が未設定です" };
  const meta = await sb.from("sync_meta").select("value").eq("key", "agent_stage_review").maybeSingle();
  const review = parseStageReview(meta.data?.value);
  const p = review?.proposals.find((x) => x.key === key) || review?.watch.find((x) => x.key === key);
  if (!review || !p) return { ok: false, error: "この提案は最新の週次見直しにありません（画面を更新してください）" };
  if (verdict === "adopt" && !review.proposals.some((x) => x.key === key)) {
    return { ok: false, error: "まだ条件を満たしていない段階です（見守りのまま）" };
  }

  const n = normalizeDecision({
    surface: "agent_stage",
    action: verdict,
    source: "dashboard",
    targetType: "agent_stage",
    targetId: `${key}@${review.week}`,
    employee: p.id,
    subject: `${p.id} ${p.name}：${p.from}→${p.to}`,
    aiProposal: [...p.reasons, ...p.blockers.map((b) => `まだ: ${b}`)].join("\n"),
    note: text || null,
    idemKey,
    payload: {
      key,
      week: review.week,
      agent_id: p.id,
      from: p.from,
      to: p.to,
      kind: p.kind,
      reasons: p.reasons,
      blockers: p.blockers,
      weeks: p.weeks.slice(0, 6),
      decisions: p.decisions,
      source_detail: "dashboard_review",
    },
  });
  if (!n.ok) return { ok: false, error: n.error };
  const { data: dup } = await sb.from("owner_decisions").select("id").eq("payload->>idem_key", n.idemKey).limit(1).maybeSingle();
  if (dup) return { ok: true, duplicate: true };
  const { error } = await sb.from("owner_decisions").insert(n.row);
  if (error && error.code !== "23505") return { ok: false, error: `記録に失敗: ${error.message}` };
  revalidatePath("/review");
  return { ok: true, duplicate: Boolean(error) };
}
