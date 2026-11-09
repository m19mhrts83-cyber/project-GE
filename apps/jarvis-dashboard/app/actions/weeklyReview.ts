"use server";

/**
 * 週次レビュー（/review）でのルール候補への判断: 採用／今回だけ／違う／ひとこと。
 * ループウェアの /rules と同じ形（surface=rule_review、payload.candidate_id）で owner_decisions に残すので、
 * 反映は従来どおり scripts/jarvis_loopware_apply_rules.py（採用だけ・1ルール=1コミット）が拾う。
 */
import { revalidatePath } from "next/cache";
import { createClient } from "@/lib/supabase/server";
import { createServiceClient } from "@/lib/supabase/admin";
import { normalizeDecision } from "@/lib/decisionContract";
import { VERDICT_ACTION, type RuleCandidate, type Verdict } from "@/lib/weeklyReview";

export type JudgeResult = { ok: true; duplicate: boolean } | { ok: false; error: string };

export async function judgeRuleCandidate(
  candidate: RuleCandidate,
  verdict: Verdict,
  idemKey: string,
  note?: string,
): Promise<JudgeResult> {
  const auth = await createClient();
  const {
    data: { user },
  } = await auth.auth.getUser();
  if (!user) return { ok: false, error: "ログインが切れています" };

  if (!(verdict in VERDICT_ACTION)) return { ok: false, error: "判断の種類が不正です" };
  if (!candidate || !/^C[0-9a-f]{8}$/.test(String(candidate.id))) return { ok: false, error: "候補が不正です" };
  if (String(idemKey || "").length < 8) return { ok: false, error: "idemKey" };
  const text = String(note || "").trim();
  if (verdict === "comment" && !text) return { ok: false, error: "ひとことが空です" };

  const sb = createServiceClient();
  if (!sb) return { ok: false, error: "Supabase が未設定です" };

  const n = normalizeDecision({
    surface: "rule_review",
    action: VERDICT_ACTION[verdict],
    source: "dashboard",
    targetType: "rule_candidate",
    targetId: candidate.id,
    employee: candidate.employee,
    idemKey,
    note: text || null,
    scope: verdict === "once" ? "once" : verdict === "accept" ? "always" : null,
    payload: {
      candidate_id: candidate.id,
      kind: candidate.kind,
      employee: candidate.employee,
      rule_line: candidate.rule_line,
      text: candidate.text,
      why: candidate.why,
      evidence: (candidate.evidence || []).slice(0, 10),
      ladder: candidate.status,
      source_detail: "dashboard_review",
    },
  });
  if (!n.ok) return { ok: false, error: n.error };

  const { data: dup } = await sb
    .from("owner_decisions")
    .select("id")
    .eq("payload->>idem_key", n.idemKey)
    .limit(1)
    .maybeSingle();
  if (dup) return { ok: true, duplicate: true };

  const { error } = await sb.from("owner_decisions").insert(n.row);
  if (error && error.code !== "23505") return { ok: false, error: `記録に失敗: ${error.message}` };
  revalidatePath("/review");
  return { ok: true, duplicate: Boolean(error) };
}
