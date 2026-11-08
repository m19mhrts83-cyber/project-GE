/**
 * メール要対応（Slack）の判断を owner_decisions に足し込む。
 * 状態の変化そのもの（sent / skipped / todoist …）は triage_items のトリガーが1行残すので、
 * ここでは後から分かること（理由タグ・迷った・送り手ルールの確認）だけを書く。
 * 失敗しても本線は止めない。
 */
import { createServiceClient } from "@/lib/supabase/admin";
import { logOwnerDecision } from "@/lib/ownerDecisionLog";
import { confirmMailSenderMute, skipPendingFromMutedSender } from "@/lib/mailActionSkipMute";
import { parseEmailAddr } from "@/lib/selfEmails";
import { weekStartIso, type MaMuteChoice, type MaReasonTag } from "@/lib/maDecisionBlocks";

function obj(raw: unknown): Record<string, unknown> {
  return raw && typeof raw === "object" && !Array.isArray(raw) ? { ...(raw as Record<string, unknown>) } : {};
}

/** 今週（月曜 JST〜）の triage 判断件数。取れなければ null */
export async function weekDecisionCount(): Promise<number | null> {
  try {
    const sb = createServiceClient();
    if (!sb) return null;
    const { count, error } = await sb
      .from("owner_decisions")
      .select("id", { count: "exact", head: true })
      .like("surface", "triage%")
      .gte("decided_at", weekStartIso());
    if (error) return null;
    return count ?? null;
  } catch {
    return null;
  }
}

/**
 * 見送りの理由タグ。triage_items と、トリガーが残した最新の判断行の両方に付ける。
 * 「迷う」は action を hesitated に替え、不要（skipped）として学ばないようにする。
 */
export async function tagSkipReason(
  id: string,
  tag: MaReasonTag,
): Promise<{ ok: boolean; who: string; fromEmail: string }> {
  const sb = createServiceClient();
  if (!sb) return { ok: false, who: "", fromEmail: "" };
  const now = new Date().toISOString();
  const { data: row } = await sb
    .from("triage_items")
    .select("id,partner,from_email,payload")
    .eq("id", id)
    .maybeSingle();
  const who = String(row?.partner || row?.from_email || "");
  const fromEmail = String(row?.from_email || "");
  if (row) {
    const pl = obj(row.payload);
    pl.skip_reason_tags = [tag];
    pl.skip_reason_at = now;
    if (tag === "hesitate") pl.hesitated = true;
    await sb.from("triage_items").update({ payload: pl }).eq("id", id);
  }
  try {
    const { data: dec } = await sb
      .from("owner_decisions")
      .select("id,action,payload")
      .eq("target_type", "triage_item")
      .eq("target_id", id)
      .order("decided_at", { ascending: false })
      .limit(1)
      .maybeSingle();
    if (dec) {
      const pl = obj(dec.payload);
      pl.reason_tags = [tag];
      pl.reason_tagged_at = now;
      const patch: Record<string, unknown> = { payload: pl };
      if (tag === "hesitate" && dec.action === "skipped") patch.action = "hesitated";
      await sb.from("owner_decisions").update(patch).eq("id", dec.id);
    }
  } catch (e) {
    console.warn(`owner_decisions tag soft-fail: ${e instanceof Error ? e.message : String(e)}`);
  }
  return { ok: Boolean(row), who, fromEmail };
}

/** 「見送りが2回目です。次からも？」への答えを反映し、ルールの確認として記録する */
export async function decideSenderMute(
  id: string,
  choice: MaMuteChoice,
): Promise<{ ok: boolean; who: string; closed: number }> {
  const sb = createServiceClient();
  if (!sb) return { ok: false, who: "", closed: 0 };
  const { data: row } = await sb
    .from("triage_items")
    .select("id,partner,from_email,subject")
    .eq("id", id)
    .maybeSingle();
  const fromEmail = String(row?.from_email || "");
  if (!row || !fromEmail) return { ok: false, who: "", closed: 0 };
  const res = await confirmMailSenderMute(fromEmail, choice);
  let closed = 0;
  if (res.muted) {
    closed = await skipPendingFromMutedSender({
      fromEmail,
      excludeId: id,
      source: "slack_ma_mute_confirmed",
    });
  }
  const sender = parseEmailAddr(fromEmail) || fromEmail.toLowerCase();
  await logOwnerDecision({
    surface: "triage_rule",
    action: choice === "partner" ? "rule_accept" : "rule_once",
    source: "slack",
    employee: "116",
    targetType: "sender",
    targetId: sender,
    subject: row.subject ? String(row.subject) : null,
    payload: {
      rule: "mute_sender",
      scope: choice === "partner" ? "partner" : "once",
      effect: choice === "partner" ? "hide" : "none",
      from_triage_item: id,
      closed_pending: closed || undefined,
    },
  });
  return { ok: true, who: String(row.partner || fromEmail), closed };
}
