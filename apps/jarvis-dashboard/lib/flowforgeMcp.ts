/**
 * Minimal Streamable HTTP MCP (JSON-RPC) for FlowForge read proxy.
 * ChatGPT Plugins → Add custom MCP server 向け。
 */
import { runWriteAction, type WriteArgs } from "@/lib/flowforgeWriteUpstream";
import {
  fetchFlowforgeShare,
  resolveShareId,
  summarizeFlowPayload,
} from "@/lib/flowforgeShareProxy";

export const FLOWFORGE_MCP_PROTOCOL = "2024-11-05";
export const FLOWFORGE_MCP_SERVER_INFO = {
  name: "jarvis-flowforge-read",
  version: "1.1.0",
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
      },
      additionalProperties: false,
    },
  },
  {
    name: "preview_flowforge_change",
    description:
      "FlowForge の許可リスト内（テスト用）フローに対する変更案を当てた差分を返す。何も書かない。confirmToken と baseUpdatedAt を返す。",
    inputSchema: {
      type: "object",
      properties: {
        shareId: { type: "string", description: "FlowForge share id（…/share/xxxx の xxxx）" },
        url: { type: "string", description: "FlowForge share URL（shareId の代わり）" },
        flowId: { type: "string", description: "flow_… 取り違え防止の確認用（共有リンクのフローと一致が必要）" },
        changes: {
          type: "object",
          description:
            "変更案。nodes: [{id, title?, description?}]、addEdges: [{source,target}]、removeEdges: [{id}|{source,target}]。ノード種別・位置の変更は不可。",
          properties: {
            nodes: { type: "array", items: { type: "object" } },
            addEdges: { type: "array", items: { type: "object" } },
            removeEdges: { type: "array", items: { type: "object" } },
          },
          additionalProperties: false,
        },
      },
      required: ["changes"],
      additionalProperties: false,
    },
    annotations: { readOnlyHint: true },
  },
  {
    name: "apply_flowforge_change",
    description:
      "FlowForge のフローへ変更を書き込む（非公式 API）。松野さんが会話で明示的に承認した後だけ呼ぶこと。preview と同じ changes、preview が返した confirmToken と expectedUpdatedAt（= baseUpdatedAt）が必須。書き込み後に読み直して一致を確認し、一致しなければ失敗を返す。",
    inputSchema: {
      type: "object",
      properties: {
        shareId: { type: "string", description: "FlowForge share id（…/share/xxxx の xxxx）" },
        url: { type: "string", description: "FlowForge share URL（shareId の代わり）" },
        flowId: { type: "string", description: "flow_… 取り違え防止の確認用（共有リンクのフローと一致が必要）" },
        changes: {
          type: "object",
          description:
            "変更案。nodes: [{id, title?, description?}]、addEdges: [{source,target}]、removeEdges: [{id}|{source,target}]。ノード種別・位置の変更は不可。",
          properties: {
            nodes: { type: "array", items: { type: "object" } },
            addEdges: { type: "array", items: { type: "object" } },
            removeEdges: { type: "array", items: { type: "object" } },
          },
          additionalProperties: false,
        },
        expectedUpdatedAt: { type: "string", description: "preview の baseUpdatedAt" },
        confirmToken: { type: "string", description: "preview の confirmToken" },
      },
      required: ["changes", "expectedUpdatedAt", "confirmToken"],
      additionalProperties: false,
    },
    annotations: { readOnlyHint: false, destructiveHint: true },
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
  const summary =
    args.summary === undefined || args.summary === null
      ? true
      : Boolean(args.summary);

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

  const payload = summary
    ? {
        ok: true,
        shareId: resolved.shareId,
        summary: summarizeFlowPayload(upstream.body),
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
    if (name === "preview_flowforge_change" || name === "apply_flowforge_change") {
      const wargs: WriteArgs = {
        shareId: typeof args.shareId === "string" ? args.shareId : null,
        url: typeof args.url === "string" ? args.url : null,
        flowId: typeof args.flowId === "string" ? args.flowId : null,
        changes: args.changes,
        expectedUpdatedAt:
          typeof args.expectedUpdatedAt === "string" ? args.expectedUpdatedAt : null,
        confirmToken: typeof args.confirmToken === "string" ? args.confirmToken : null,
      };
      const out = await runWriteAction(
        name === "preview_flowforge_change" ? "preview" : "apply",
        wargs,
      );
      return rpcResult(id, {
        content: [{ type: "text", text: JSON.stringify(out.body, null, 2) }],
        isError: out.status >= 400,
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
