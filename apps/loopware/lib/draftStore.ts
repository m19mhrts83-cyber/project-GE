/** 下書きレビューの保存（サーバ専用）。表は draft_reviews（20261109 migration） */
import type { SupabaseClient } from "@supabase/supabase-js";
import { writeDecision } from "@/lib/ownerDecisionLog";
import { commentsNote, diffStats, diffText, type DraftComment, type DraftVersion } from "@/lib/draftCore";

export const CHANNELS = ["chatwork", "mail", "line", "slack", "doc", "other"] as const;

export type DraftRow = {
  id: string;
  case_name: string;
  recipient: string;
  channel: string;
  status: "open" | "done" | "dropped";
  context: string | null;
  versions: DraftVersion[];
  source: string;
  created_at: string;
  updated_at: string;
};

export async function getDraft(sb: SupabaseClient, id: string): Promise<DraftRow | null> {
  const { data } = await sb.from("draft_reviews").select("*").eq("id", id).maybeSingle();
  return (data as DraftRow) || null;
}

/** 楽観ロック: 読んだときの updated_at が変わっていたら保存しない（二つの端末で同時に直したとき） */
export async function saveVersions(
  sb: SupabaseClient,
  row: DraftRow,
  versions: DraftVersion[],
  status?: DraftRow["status"],
): Promise<{ ok: true; row: DraftRow } | { ok: false; error: string }> {
  const patch: Record<string, unknown> = { versions, updated_at: new Date().toISOString() };
  if (status) patch.status = status;
  const { data, error } = await sb
    .from("draft_reviews")
    .update(patch)
    .eq("id", row.id)
    .eq("updated_at", row.updated_at)
    .select("*")
    .maybeSingle();
  if (error) return { ok: false, error: error.message };
  if (!data) return { ok: false, error: "ほかの端末で更新されました。読み直してください" };
  return { ok: true, row: data as DraftRow };
}

/** 版が1つ進んだ = 松野さんの判断1件。owner_decisions に surface=draft_review で残す */
export async function logRevision(
  sb: SupabaseClient,
  row: DraftRow,
  from: DraftVersion,
  to: DraftVersion,
  action: "revise" | "wrong" | "adopt",
  extra: { comments?: DraftComment[]; ruleHint?: string; note?: string } = {},
) {
  const comments = extra.comments || [];
  const stats = diffStats(diffText(from.text, to.text));
  return writeDecision(sb, {
    surface: "draft_review",
    action,
    source: "loopware",
    targetType: "draft",
    targetId: `${row.id}:${from.label}->${to.label}`,
    idemKey: `draft:${row.id}:${from.label}->${to.label}:${action}`,
    employee: "211",
    subject: row.case_name,
    partner: row.recipient,
    aiProposal: from.text,
    finalText: to.text,
    note: extra.note || commentsNote(comments) || null,
    voice: comments.some((c) => c.via === "voice")
      ? { segments: comments.filter((c) => c.via === "voice").map((c) => ({ target: c.quote || "全体", text: c.text })) }
      : null,
    payload: {
      case: row.case_name,
      recipient: row.recipient,
      channel: row.channel,
      draft_id: row.id,
      version_from: from.label,
      version_to: to.label,
      by: to.by,
      comments,
      reason: commentsNote(comments) || extra.note || undefined,
      reason_missing: !comments.length && !extra.note,
      rule_hint: extra.ruleHint || undefined,
      places: stats.places,
      chars_added: stats.added,
      chars_removed: stats.removed,
    },
  });
}
