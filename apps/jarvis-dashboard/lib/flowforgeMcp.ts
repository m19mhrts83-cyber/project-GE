/**
 * Minimal Streamable HTTP MCP (JSON-RPC) for FlowForge read proxy.
 * ChatGPT Plugins → Add custom MCP server 向け。
 *
 * 2026-11-21: 編集用の読み取り（view=edit）と、修正文の待ち箱
 * （queue_flowforge_edit / get_flowforge_edit_status）を追加。
 * FlowForge へ直接は書かない。待ち箱は Mac のプログラムが拾う。
 */
import {
  fetchFlowforgeShare,
  resolveShareId,
  summarizeFlowPayload,
} from "@/lib/flowforgeShareProxy";
import { editViewFlowPayload } from "@/lib/flowforgeEditView";
import {
  getFlowforgeEditStatus,
  queueFlowforgeEdit,
  queueFlowforgeUndo,
} from "@/lib/flowforgeEditQueue";

export const FLOWFORGE_MCP_PROTOCOL = "2024-11-05";
export const FLOWFORGE_MCP_SERVER_INFO = {
  name: "jarvis-flowforge-read",
  version: "1.2.0",
};

type JsonRpcId = string | number | null;

export type JsonRpcRequest = {
  jsonrpc?: string;
  id?: JsonRpcId;
  method?: string;
  params?: Record<string, unknown>;
};

export type JsonRpcResponse = {
  jsonrpc: "2.0";
  id: JsonRpcId;
  result?: unknown;
  error?: { code: number; message: string; data?: unknown };
};

const TOOLS = [
  {
    name: "resolve_flowforge_flow",
    description:
      "Read-only: fetch a FlowForge (AI Automation) workflow by share URL, shareId, flowId, or agentId (e.g. 312). Prefer summary=true to save tokens. Use when the user pastes a FlowForge link or asks to review a flow.",
    inputSchema: {
      type: "object",
      properties: {
        url: {
          type: "string",
          description:
            "FlowForge share or edit URL (…/share/… or …/flows/flow_…)",
        },
        shareId: { type: "string", description: "Bare share id" },
        flowId: {
          type: "string",
          description: "flow_… id (resolved via agent registry share URL)",
        },
        agentId: {
          type: "string",
          description: "Agent team id such as 312",
        },
        summary: {
          type: "boolean",
          description: "If true (default), return node titles only",
          default: true,
        },
        view: {
          type: "string",
          enum: ["summary", "edit", "full"],
          description:
            "summary = ids/kinds/titles only. edit = what you need to write edit instructions: node id/kind/title/description/tool/parent subflow plus edges (from→to, label) and unconnected nodes, no coordinates. full = raw JSON. Use edit before proposing changes and again after an edit to verify. Overrides summary.",
        },
      },
      additionalProperties: false,
    },
  },
  {
    name: "queue_flowforge_edit",
    description:
      "Put edit instructions for one agent's FlowForge flow into a waiting box. A program on the owner's Mac types them into FlowForge's own AI assistant in the owner's browser. Call ONLY after the user has read the exact instruction text in this chat and said to apply it; set confirmedByUser=true only then. Keep each request small (up to about 4 changes, max 6 list items, 2000 chars), one operation per line, refer to nodes by their exact current titles, and do not delete nodes unless the user asked. Does not write to FlowForge directly; the Mac must be awake.",
    inputSchema: {
      type: "object",
      properties: {
        agentId: { type: "string", description: "Agent team id such as 311" },
        instructions: {
          type: "string",
          description: "Japanese instruction text to send to FlowForge's AI assistant",
        },
        confirmedByUser: {
          type: "boolean",
          description: "true only if the user approved this exact text in the chat",
        },
        note: { type: "string", description: "Optional short memo (why)" },
      },
      required: ["agentId", "instructions", "confirmedByUser"],
      additionalProperties: false,
    },
  },
  {
    name: "get_flowforge_edit_status",
    description:
      "Read the state of a queued edit (queued / running / sent / error), the FlowForge AI assistant's reply, and what actually changed: edges_added / edges_removed / nodes_added / nodes_removed. FlowForge sometimes makes changes that were not asked for (it may drop an existing arrow or auto-connect isolated nodes), so always compare these lists with the request and tell the user about anything extra. If something extra happened, offer undo_flowforge_edit.",
    inputSchema: {
      type: "object",
      properties: { id: { type: "string", description: "id returned by queue_flowforge_edit" } },
      required: ["id"],
      additionalProperties: false,
    },
  },
  {
    name: "undo_flowforge_edit",
    description:
      "Undo one sent edit: the Mac program presses FlowForge's own Undo until the flow is back to the state just before that edit. Use right after an edit whose result had unrequested changes. Call only after the user said to undo it (confirmedByUser=true). Check the outcome with get_flowforge_edit_status on the returned id (reached_target=true means fully restored).",
    inputSchema: {
      type: "object",
      properties: {
        id: { type: "string", description: "id of the sent edit to undo" },
        confirmedByUser: { type: "boolean", description: "true only if the user asked to undo" },
      },
      required: ["id", "confirmedByUser"],
      additionalProperties: false,
    },
  },
] as const;

function rpcResult(id: JsonRpcId, result: unknown): JsonRpcResponse {
  return { jsonrpc: "2.0", id, result };
}

function rpcError(
  id: JsonRpcId,
  code: number,
  message: string,
  data?: unknown,
): JsonRpcResponse {
  return { jsonrpc: "2.0", id, error: { code, message, data } };
}

async function callResolveFlow(
  args: Record<string, unknown>,
): Promise<{ text: string; isError: boolean }> {
  const url = typeof args.url === "string" ? args.url : null;
  const shareId = typeof args.shareId === "string" ? args.shareId : null;
  const flowId = typeof args.flowId === "string" ? args.flowId : null;
  const agentId = typeof args.agentId === "string" ? args.agentId : null;
  const viewArg = typeof args.view === "string" ? args.view : "";
  const view: "summary" | "edit" | "full" =
    viewArg === "edit" || viewArg === "full" || viewArg === "summary"
      ? viewArg
      : args.summary === undefined || args.summary === null || Boolean(args.summary)
        ? "summary"
        : "full";

  const resolved = resolveShareId({ shareId, url, flowId, agentId });
  if ("error" in resolved) {
    return {
      isError: true,
      text: JSON.stringify({ ok: false, error: resolved.error }),
    };
  }

  const upstream = await fetchFlowforgeShare(resolved.shareId);
  if (!upstream.ok) {
    return {
      isError: true,
      text: JSON.stringify({
        ok: false,
        error: upstream.error,
        upstream: upstream.upstream ?? null,
        shareId: resolved.shareId,
      }),
    };
  }

  const payload =
    view === "summary"
      ? {
          ok: true,
          shareId: resolved.shareId,
          summary: summarizeFlowPayload(upstream.body),
        }
      : view === "edit"
        ? {
            ok: true,
            shareId: resolved.shareId,
            note: "共有リンクの内容です。編集直後は updatedAt が変わったかを見て、最新かどうか確かめてください。",
            edit: editViewFlowPayload(upstream.body),
          }
        : {
            ok: true,
            shareId: resolved.shareId,
            ...(upstream.body as object),
          };
  return { isError: false, text: JSON.stringify(payload, null, 2) };
}

export async function handleFlowforgeMcpRequest(
  body: JsonRpcRequest,
): Promise<JsonRpcResponse | null> {
  const method = (body.method || "").trim();
  const id = body.id === undefined ? null : body.id;
  const params = (body.params || {}) as Record<string, unknown>;

  // Notifications (no response)
  if (id === null || id === undefined) {
    if (
      method === "notifications/initialized" ||
      method === "notifications/cancelled"
    ) {
      return null;
    }
  }

  if (method === "initialize") {
    return rpcResult(id, {
      protocolVersion: FLOWFORGE_MCP_PROTOCOL,
      capabilities: { tools: {} },
      serverInfo: FLOWFORGE_MCP_SERVER_INFO,
    });
  }

  if (method === "ping") {
    return rpcResult(id, {});
  }

  if (method === "tools/list") {
    return rpcResult(id, { tools: TOOLS });
  }

  if (method === "tools/call") {
    const name = String(params.name || "");
    const args =
      params.arguments && typeof params.arguments === "object"
        ? (params.arguments as Record<string, unknown>)
        : {};
    if (
      name === "queue_flowforge_edit" ||
      name === "get_flowforge_edit_status" ||
      name === "undo_flowforge_edit"
    ) {
      const res =
        name === "queue_flowforge_edit"
          ? await queueFlowforgeEdit(args)
          : name === "undo_flowforge_edit"
            ? await queueFlowforgeUndo(args)
            : await getFlowforgeEditStatus(args);
      return rpcResult(id, {
        content: [{ type: "text", text: JSON.stringify(res, null, 2) }],
        isError: !res.ok,
      });
    }
    if (name !== "resolve_flowforge_flow") {
      return rpcError(id, -32601, `Unknown tool: ${name}`);
    }
    const out = await callResolveFlow(args);
    return rpcResult(id, {
      content: [{ type: "text", text: out.text }],
      isError: out.isError,
    });
  }

  if (!method) {
    return rpcError(id, -32600, "Invalid Request");
  }
  return rpcError(id, -32601, `Method not found: ${method}`);
}
