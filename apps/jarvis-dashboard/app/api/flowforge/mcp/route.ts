import { NextResponse, type NextRequest } from "next/server";
import {
  handleFlowforgeMcpRequest,
  type JsonRpcRequest,
} from "@/lib/flowforgeMcp";
import { proxyAuthorized } from "@/lib/flowforgeShareProxy";

export const runtime = "nodejs";
export const maxDuration = 30;

const CORS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
  "Access-Control-Allow-Headers":
    "Authorization, Content-Type, Accept, Mcp-Session-Id, Last-Event-ID",
  "Access-Control-Expose-Headers": "Mcp-Session-Id",
};

function unauthorized(secretSet: boolean) {
  return NextResponse.json(
    {
      jsonrpc: "2.0",
      id: null,
      error: {
        code: -32001,
        message: secretSet
          ? "unauthorized"
          : "FLOWFORGE_READ_PROXY_KEY 未設定",
      },
    },
    { status: secretSet ? 401 : 503, headers: CORS },
  );
}

export async function OPTIONS() {
  return new NextResponse(null, { status: 204, headers: CORS });
}

/** Health / discovery for some clients */
export async function GET(request: NextRequest) {
  if ((process.env.FLOWFORGE_READ_PROXY_DISABLE || "").trim() === "1") {
    return NextResponse.json(
      { ok: false, error: "disabled" },
      { status: 503, headers: CORS },
    );
  }
  const secretSet = Boolean((process.env.FLOWFORGE_READ_PROXY_KEY || "").trim());
  if (!proxyAuthorized(request.headers, request.nextUrl)) {
    return unauthorized(secretSet);
  }
  return NextResponse.json(
    {
      ok: true,
      transport: "streamable-http",
      mcp: "/api/flowforge/mcp",
      tools: ["resolve_flowforge_flow"],
      auth: "Bearer または ?key=（ChatGPT カスタムMCPは後者）",
    },
    { headers: CORS },
  );
}

/**
 * Streamable HTTP MCP endpoint (JSON-RPC over POST).
 * Auth: Authorization: Bearer $FLOWFORGE_READ_PROXY_KEY
 * ChatGPT: Plugins → 追加 → カスタム MCP サーバー
 *   URL: https://jarvis-dashboard-amber.vercel.app/api/flowforge/mcp
 */
export async function POST(request: NextRequest) {
  if ((process.env.FLOWFORGE_READ_PROXY_DISABLE || "").trim() === "1") {
    return NextResponse.json(
      {
        jsonrpc: "2.0",
        id: null,
        error: { code: -32000, message: "disabled" },
      },
      { status: 503, headers: CORS },
    );
  }
  const secretSet = Boolean((process.env.FLOWFORGE_READ_PROXY_KEY || "").trim());
  if (!proxyAuthorized(request.headers, request.nextUrl)) {
    return unauthorized(secretSet);
  }

  let body: JsonRpcRequest;
  try {
    body = (await request.json()) as JsonRpcRequest;
  } catch {
    return NextResponse.json(
      {
        jsonrpc: "2.0",
        id: null,
        error: { code: -32700, message: "Parse error" },
      },
      { status: 400, headers: CORS },
    );
  }

  const response = await handleFlowforgeMcpRequest(body);
  if (response === null) {
    return new NextResponse(null, { status: 202, headers: CORS });
  }
  return NextResponse.json(response, { headers: CORS });
}
