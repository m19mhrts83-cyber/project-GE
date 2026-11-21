/**
 * FlowForge 修正文の待ち箱（2026-11-21）。
 *
 * ChatGPT が MCP で「本人が了承した修正文」を置く → Mac のプログラム
 * （scripts/jarvis_flowforge_assistant_paste.py --queue-once）が拾い、
 * 本人の Chrome で FlowForge の AIアシスタントへ入力・送信する。
 *
 * ここは FlowForge へ直接書かない（書き込み口が無い）。置き場は Supabase。
 */
import { getAgentById } from "@/lib/agentTeam";
import { createServiceClient } from "@/lib/supabase/admin";
import { checkEditRequest, EDIT_QUEUE_MAX_WAITING } from "@/lib/flowforgeEditView";

const TABLE = "flowforge_edit_queue";

export type QueueResult = { ok: true; data: Record<string, unknown> } | { ok: false; error: string };

export async function queueFlowforgeEdit(args: Record<string, unknown>): Promise<QueueResult> {
  const checked = checkEditRequest(args);
  if (!checked.ok) return checked;
  const agent = getAgentById(checked.agentId);
  if (!agent?.flowforge_id) return { ok: false, error: "flow_not_registered_for_agent" };
  const sb = createServiceClient();
  if (!sb) return { ok: false, error: "queue_storage_not_configured" };

  const waiting = await sb
    .from(TABLE)
    .select("id", { count: "exact", head: true })
    .in("status", ["queued", "running"]);
  if (waiting.error) return { ok: false, error: "queue_read_failed" };
  if ((waiting.count || 0) >= EDIT_QUEUE_MAX_WAITING) {
    return { ok: false, error: "queue_full_wait_for_mac" };
  }

  const ins = await sb
    .from(TABLE)
    .insert({
      agent_id: checked.agentId,
      flow_id: agent.flowforge_id,
      instructions: checked.instructions,
      note: typeof args.note === "string" ? args.note.slice(0, 300) : null,
    })
    .select("id, agent_id, flow_id, status, created_at")
    .single();
  if (ins.error || !ins.data) return { ok: false, error: "queue_insert_failed" };
  return {
    ok: true,
    data: {
      ...ins.data,
      next: "Mac のプログラムが拾って FlowForge の AIアシスタントへ送ります。get_flowforge_edit_status で結果を確かめてください。",
    },
  };
}

export async function getFlowforgeEditStatus(args: Record<string, unknown>): Promise<QueueResult> {
  const id = typeof args.id === "string" ? args.id.trim() : "";
  if (!/^[0-9a-f-]{36}$/i.test(id)) return { ok: false, error: "id_required" };
  const sb = createServiceClient();
  if (!sb) return { ok: false, error: "queue_storage_not_configured" };
  const row = await sb
    .from(TABLE)
    .select("id, agent_id, flow_id, status, result, error, created_at, started_at, finished_at")
    .eq("id", id)
    .maybeSingle();
  if (row.error) return { ok: false, error: "queue_read_failed" };
  if (!row.data) return { ok: false, error: "not_found" };
  return { ok: true, data: row.data };
}
