/**
 * FlowForge の「編集用の読み取り」と「修正文の待ち箱」の純粋な部品。
 * （"@/..." を読み込まない。node --test から直接読める）
 *
 * 編集用の読み取り: 修正文を書くのに要るものだけ（ID・種別・タイトル・説明・道具・
 * 所属サブフロー・矢印）。座標や見た目は返さない。
 */

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
  if (!/^\d{3}$/.test(agentId)) {
    return { ok: false, error: "agentId_required_3_digits" };
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
