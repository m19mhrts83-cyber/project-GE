/**
 * FlowForge の「編集用の読み取り」と「修正文の待ち箱」の純粋な部品。
 * （"@/..." を読み込まない。node --test から直接読める）
 *
 * 編集用の読み取り: 修正文を書くのに要るものだけ（ID・種別・タイトル・説明・道具・
 * 所属サブフロー・矢印）。座標や見た目は返さない。
 */

/** 社員番号。3桁、または複数フローの枝（例: 315-B）。 */
export const AGENT_ID_RE = /^\d{3}(-[A-Z])?$/;

export type EditViewNode = {
  id: string;
  kind: string;
  subtype?: string;
  title: string;
  toolName?: string;
  meta?: string;
  description?: string;
  parentId?: string;
  parentTitle?: string;
};

export type EditViewEdge = {
  id: string;
  from: string;
  to: string;
  fromTitle: string;
  toTitle: string;
  label?: string;
};

export type EditView = {
  id: string | null;
  name: string | null;
  description: string | null;
  updatedAt: string | null;
  node_count: number;
  edge_count: number;
  nodes: EditViewNode[];
  edges: EditViewEdge[];
  /** どこからも矢印が入らず、どこへも出ていないノード（開始・終了・サブフローの中を除く） */
  unconnected: string[];
};

function str(v: unknown): string {
  return typeof v === "string" ? v : v == null ? "" : String(v);
}

export function editViewFlowPayload(payload: unknown): EditView {
  const root = (payload && typeof payload === "object" ? payload : {}) as {
    flow?: Record<string, unknown>;
  };
  const flow = (root.flow || {}) as Record<string, unknown>;
  const rawNodes = Array.isArray(flow.nodes) ? (flow.nodes as Array<Record<string, unknown>>) : [];
  const rawEdges = Array.isArray(flow.edges) ? (flow.edges as Array<Record<string, unknown>>) : [];

  const titleOf: Record<string, string> = {};
  for (const n of rawNodes) {
    const data = (n.data || {}) as Record<string, unknown>;
    titleOf[str(n.id)] = str(data.title) || str(data.toolName);
  }

  const nodes: EditViewNode[] = rawNodes.map((n) => {
    const data = (n.data || {}) as Record<string, unknown>;
    const out: EditViewNode = {
      id: str(n.id),
      kind: str(data.kind) || str(n.type) || "?",
      title: str(data.title) || str(data.toolName),
    };
    if (str(data.subtype)) out.subtype = str(data.subtype);
    if (str(data.toolName)) out.toolName = str(data.toolName);
    if (str(data.meta)) out.meta = str(data.meta);
    if (str(data.description)) out.description = str(data.description);
    if (str(n.parentId)) {
      out.parentId = str(n.parentId);
      out.parentTitle = titleOf[str(n.parentId)] || "";
    }
    return out;
  });

  const edges: EditViewEdge[] = rawEdges.map((e) => {
    const out: EditViewEdge = {
      id: str(e.id),
      from: str(e.source),
      to: str(e.target),
      fromTitle: titleOf[str(e.source)] || "",
      toTitle: titleOf[str(e.target)] || "",
    };
    const data = (e.data || {}) as Record<string, unknown>;
    const label = str(e.label) || str(data.label) || str(data.condition);
    if (label) out.label = label;
    return out;
  });

  const touched = new Set<string>();
  for (const e of edges) {
    touched.add(e.from);
    touched.add(e.to);
  }
  const unconnected = nodes
    .filter((n) => !touched.has(n.id) && !n.parentId && n.kind !== "start" && n.kind !== "end")
    .map((n) => n.title || n.id);

  return {
    id: str(flow.id) || null,
    name: str(flow.name) || null,
    description: str(flow.description) || null,
    updatedAt: str(flow.updatedAt) || null,
    node_count: nodes.length,
    edge_count: edges.length,
    nodes,
    edges,
    unconnected,
  };
}

/* ---------- 修正文の待ち箱 ---------- */

export const EDIT_INSTRUCTIONS_MAX_CHARS = 2000;
export const EDIT_INSTRUCTIONS_MAX_ITEMS = 6;
export const EDIT_QUEUE_MAX_WAITING = 5;

export type EditRequestCheck =
  | { ok: true; agentId: string; instructions: string }
  | { ok: false; error: string };

/**
 * 待ち箱へ入れる前の点検。
 * - 本人が文面を了承した（confirmedByUser === true）ものだけ
 * - 1回に入れる項目は少なく（小分け。AIアシスタントが崩しにくい）
 */
export function checkEditRequest(args: Record<string, unknown>): EditRequestCheck {
  const agentId = str(args.agentId).trim();
  if (!AGENT_ID_RE.test(agentId)) {
    return { ok: false, error: "agentId_required_3_digits_or_with_letter" };
  }
  if (args.confirmedByUser !== true) {
    return { ok: false, error: "user_confirmation_required" };
  }
  const instructions = str(args.instructions).replace(/\r\n/g, "\n").trim();
  if (!instructions) return { ok: false, error: "instructions_required" };
  if (instructions.length > EDIT_INSTRUCTIONS_MAX_CHARS) {
    return { ok: false, error: `instructions_too_long_max_${EDIT_INSTRUCTIONS_MAX_CHARS}` };
  }
  const items = instructions.split("\n").filter((l) => /^\s*(\d+[.)．、]|[-・*])\s*\S/.test(l));
  if (items.length > EDIT_INSTRUCTIONS_MAX_ITEMS) {
    return { ok: false, error: `too_many_items_max_${EDIT_INSTRUCTIONS_MAX_ITEMS}_split_request` };
  }
  return { ok: true, agentId, instructions };
}

/* ---------- 直接編集（AIアシスタントを通さない）の依頼の点検 ---------- */

export const PATCH_MAX_OPS = 12;
export const PATCH_TEXT_MAX = 2000;
const PATCHABLE_KEYS = ["title", "description", "meta", "toolName"];

export type PatchOp =
  | { op: "update_node"; id: string; patch: Record<string, string> }
  | { op: "add_edge"; source: string; target: string; replace?: boolean }
  | { op: "remove_edge"; id?: string; source?: string; target?: string };

export type PatchRequestCheck =
  | { ok: true; agentId: string; operations: PatchOp[] }
  | { ok: false; error: string };

/**
 * 形だけを点検する（ノードや矢印が実在するか・既存の矢印とぶつかるかは、
 * 最新の状態を持つ Mac 側が実行の直前に点検する）。
 */
export function checkPatchRequest(args: Record<string, unknown>): PatchRequestCheck {
  const agentId = str(args.agentId).trim();
  if (!AGENT_ID_RE.test(agentId)) return { ok: false, error: "agentId_required_3_digits_or_with_letter" };
  if (args.confirmedByUser !== true) return { ok: false, error: "user_confirmation_required" };
  const raw = args.operations;
  if (!Array.isArray(raw) || raw.length === 0) return { ok: false, error: "operations_required" };
  if (raw.length > PATCH_MAX_OPS) return { ok: false, error: `too_many_operations_max_${PATCH_MAX_OPS}` };
  const operations: PatchOp[] = [];
  for (let i = 0; i < raw.length; i++) {
    const o = (raw[i] && typeof raw[i] === "object" ? raw[i] : {}) as Record<string, unknown>;
    const at = `operations[${i}]`;
    if (o.op === "update_node") {
      const id = str(o.id).trim();
      const patch = (o.patch && typeof o.patch === "object" ? o.patch : null) as Record<string, unknown> | null;
      if (!id) return { ok: false, error: `${at}_id_required` };
      if (!patch || Object.keys(patch).length === 0) return { ok: false, error: `${at}_patch_required` };
      const clean: Record<string, string> = {};
      for (const [k, val] of Object.entries(patch)) {
        if (!PATCHABLE_KEYS.includes(k)) return { ok: false, error: `${at}_field_not_allowed_${k}` };
        if (typeof val !== "string") return { ok: false, error: `${at}_${k}_must_be_string` };
        if (val.length > PATCH_TEXT_MAX) return { ok: false, error: `${at}_${k}_too_long` };
        clean[k] = val;
      }
      if ("title" in clean && !clean.title.trim()) return { ok: false, error: `${at}_title_empty` };
      operations.push({ op: "update_node", id, patch: clean });
    } else if (o.op === "add_edge") {
      const source = str(o.source).trim();
      const target = str(o.target).trim();
      if (!source || !target) return { ok: false, error: `${at}_source_and_target_required` };
      if (source === target) return { ok: false, error: `${at}_source_equals_target` };
      operations.push(
        o.replace === true ? { op: "add_edge", source, target, replace: true } : { op: "add_edge", source, target },
      );
    } else if (o.op === "remove_edge") {
      const id = str(o.id).trim();
      const source = str(o.source).trim();
      const target = str(o.target).trim();
      if (id) operations.push({ op: "remove_edge", id });
      else if (source && target) operations.push({ op: "remove_edge", source, target });
      else return { ok: false, error: `${at}_id_or_source_target_required` };
    } else {
      return { ok: false, error: `${at}_unknown_op` };
    }
  }
  return { ok: true, agentId, operations };
}
