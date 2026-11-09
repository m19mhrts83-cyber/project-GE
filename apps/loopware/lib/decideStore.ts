import type { SupabaseClient } from "@supabase/supabase-js";

/**
 * Loopware の判断を共有DBへ残す（/api/decide 本体）。
 * - 312 → task_loop_topics / task_loop_proposals / task_loop_decisions
 *   同じ話題（agent 312 × topic_text）は topic を使い回す。同じ判断の送り直しは行を増やさない。
 *   判断を変えたときは前の判断を history に積む（監査用に残す）。
 * - 313 → owner_decisions（1判断1行）。同じタスク・同じ判断を 10 分以内に送り直したら増やさない。
 * どの書き込みも error を確かめ、失敗は persisted:false で返す（成功に見せない）。
 */

export type DecideBody = {
  agentId?: string;
  topicText?: string;
  seedId?: string;
  proposals?: { index: number; label: string; body: string }[];
  decision?: {
    choice: string;
    chosenIndex?: number;
    finalText?: string;
    beforeText?: string;
    afterText?: string;
    reasonTags?: string[];
    freeNote?: string;
    decidedVia?: string;
    /** once＝今回だけ／rule＝次も同じに（基準の候補） */
    scope?: string;
  };
  todoistTaskId?: string | null;
};

export type DecideResult = {
  ok: boolean;
  persisted: boolean;
  deduped?: boolean;
  via?: "owner_decisions" | "task_loop";
  topicId?: string;
  reason?: string;
};

export const DEDUPE_313_MS = 10 * 60 * 1000;

function sameTags(a: unknown, b: unknown): boolean {
  const x = [...((a as string[]) || [])].sort().join("\u0001");
  const y = [...((b as string[]) || [])].sort().join("\u0001");
  return x === y;
}

async function decide313(
  sb: SupabaseClient,
  body: DecideBody,
  now: Date,
): Promise<DecideResult> {
  const d = body.decision!;
  const targetId = body.todoistTaskId || body.seedId || "-";
  const note = d.freeNote || null;
  const tags = d.reasonTags || [];

  const { data: last, error: lErr } = await sb
    .from("owner_decisions")
    .select("id, action, note, payload, decided_at")
    .eq("surface", "todoist_313")
    .eq("target_id", targetId)
    .order("decided_at", { ascending: false })
    .limit(1);
  if (lErr) return { ok: true, persisted: false, reason: lErr.message };
  const prev = (last || [])[0] as
    | { action: string; note: string | null; payload: Record<string, unknown>; decided_at: string }
    | undefined;
  if (
    prev &&
    prev.payload?.kind === "loopware" &&
    prev.action === d.choice &&
    (prev.note || null) === note &&
    sameTags(prev.payload?.reason_tags, tags) &&
    now.getTime() - new Date(prev.decided_at).getTime() < DEDUPE_313_MS
  ) {
    return { ok: true, persisted: true, deduped: true, via: "owner_decisions" };
  }

  const { error } = await sb.from("owner_decisions").insert({
    surface: "todoist_313",
    action: d.choice,
    source: d.decidedVia || "app",
    employee: "313",
    target_type: "todoist_task",
    target_id: targetId,
    subject: (body.topicText || "").slice(0, 500),
    note,
    payload: {
      kind: "loopware",
      proposals: body.proposals || null,
      chosen_index: d.chosenIndex ?? null,
      reason_tags: tags,
      final_text: d.finalText || null,
      before_text: d.beforeText || null,
      after_text: d.afterText || null,
      scope: d.scope || "once",
      // この画面は判断の記録だけ。Todoist の実処置は Slack／CLI 側
      todoist_applied: false,
    },
  });
  if (error) return { ok: true, persisted: false, reason: error.message };
  return { ok: true, persisted: true, via: "owner_decisions" };
}

async function decide312(
  sb: SupabaseClient,
  body: DecideBody,
  now: Date,
): Promise<DecideResult> {
  const d = body.decision!;
  const topicText = body.topicText || body.seedId || "";

  // 同じ話題は topic を使い回す（送り直しで topic が増えないように）
  const { data: found, error: fErr } = await sb
    .from("task_loop_topics")
    .select("id")
    .eq("agent_id", "312")
    .eq("topic_text", topicText)
    .order("created_at", { ascending: false })
    .limit(1);
  if (fErr) return { ok: true, persisted: false, reason: fErr.message };

  let topicId = ((found || [])[0] as { id: string } | undefined)?.id;
  if (!topicId) {
    const { data: topic, error: tErr } = await sb
      .from("task_loop_topics")
      .insert({
        agent_id: "312",
        source_kind: body.seedId?.startsWith("seed-") ? "seed" : "manual",
        topic_text: topicText,
        status: "decided",
      })
      .select("id")
      .single();
    if (tErr || !topic) {
      return { ok: true, persisted: false, reason: tErr?.message || "topic insert failed" };
    }
    topicId = (topic as { id: string }).id;
  }

  const props = body.proposals || [];
  if (props.length) {
    const { error: pErr } = await sb.from("task_loop_proposals").upsert(
      props.map((p) => ({
        topic_id: topicId,
        proposal_index: p.index,
        label: p.label,
        body: p.body,
        prompt_version: "seed-v1",
      })),
      { onConflict: "topic_id,proposal_index" },
    );
    if (pErr) return { ok: true, persisted: false, reason: pErr.message, topicId };
  }

  const { data: existing, error: eErr } = await sb
    .from("task_loop_decisions")
    .select("*")
    .eq("topic_id", topicId)
    .limit(1);
  if (eErr) return { ok: true, persisted: false, reason: eErr.message, topicId };
  const prev = ((existing || [])[0] || null) as Record<string, unknown> | null;

  const next = {
    topic_id: topicId,
    chosen_index: d.chosenIndex ?? null,
    choice: d.choice,
    final_text: d.finalText || null,
    before_text: d.beforeText || null,
    after_text: d.afterText || null,
    reason_tags: d.reasonTags || [],
    free_note:
      d.scope === "rule"
        ? `【次も同じに】${d.freeNote || ""}`.trim()
        : d.freeNote || null,
    decided_via: d.decidedVia || "app",
  };

  if (
    prev &&
    prev.choice === next.choice &&
    (prev.chosen_index ?? null) === next.chosen_index &&
    (prev.final_text ?? null) === next.final_text &&
    (prev.free_note ?? null) === next.free_note &&
    sameTags(prev.reason_tags, next.reason_tags)
  ) {
    return { ok: true, persisted: true, deduped: true, via: "task_loop", topicId };
  }

  const history = [
    ...(((prev?.history as unknown[]) || []) as unknown[]),
    ...(prev
      ? [
          {
            choice: prev.choice,
            chosen_index: prev.chosen_index ?? null,
            final_text: prev.final_text ?? null,
            reason_tags: prev.reason_tags || [],
            free_note: prev.free_note ?? null,
            decided_at: prev.updated_at || prev.created_at || null,
          },
        ]
      : []),
  ];

  const { error: dErr } = await sb.from("task_loop_decisions").upsert(
    { ...next, history, updated_at: now.toISOString() },
    { onConflict: "topic_id" },
  );
  if (dErr) return { ok: true, persisted: false, reason: dErr.message, topicId };
  return { ok: true, persisted: true, via: "task_loop", topicId };
}

export async function persistDecision(
  sb: SupabaseClient,
  body: DecideBody,
  now: Date = new Date(),
): Promise<DecideResult> {
  if (!body.decision) return { ok: false, persisted: false, reason: "no decision" };
  try {
    return body.agentId === "313"
      ? await decide313(sb, body, now)
      : await decide312(sb, body, now);
  } catch (e) {
    return { ok: true, persisted: false, reason: e instanceof Error ? e.message : String(e) };
  }
}
