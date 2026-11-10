import { NextResponse, type NextRequest } from "next/server";
import { createServiceClient } from "@/lib/supabase/admin";
import { enqueueDailyReview, submitKeyMatches, validateDailyReview } from "@/lib/obsidianReviewInbox";

export const runtime = "nodejs";
export const maxDuration = 15;

const MAX_BODY_BYTES = 768 * 1024;
const CORS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
  "Access-Control-Allow-Headers": "Authorization, Content-Type, Accept, Mcp-Protocol-Version",
};

type RpcRequest = {
  jsonrpc?: string;
  id?: string | number | null;
  method?: string;
  params?: Record<string, unknown>;
};

function authorized(request: NextRequest): boolean {
  const header = request.headers.get("authorization")?.replace(/^Bearer\s+/i, "");
  // Never accept credentials from URLs: query strings can be recorded in logs and history.
  const supplied = (header || "").trim();
  return submitKeyMatches(supplied);
}

function rpc(id: RpcRequest["id"], result: unknown) {
  return NextResponse.json({ jsonrpc: "2.0", id: id ?? null, result }, { headers: CORS });
}

function rpcError(id: RpcRequest["id"], code: number, message: string) {
  return NextResponse.json(
    { jsonrpc: "2.0", id: id ?? null, error: { code, message } },
    { headers: CORS },
  );
}

export async function OPTIONS() {
  return new NextResponse(null, { status: 204, headers: CORS });
}

export async function GET(request: NextRequest) {
  if (!authorized(request)) {
    return NextResponse.json({ ok: false, error: "unauthorized" }, { status: 401, headers: CORS });
  }
  return NextResponse.json(
    { ok: true, transport: "streamable-http", tools: ["submit_daily_review"] },
    { headers: CORS },
  );
}

/** A narrowly scoped MCP endpoint: ChatGPT can submit daily review notes only. */
export async function POST(request: NextRequest) {
  if (!authorized(request)) {
    return NextResponse.json({ ok: false, error: "unauthorized" }, { status: 401, headers: CORS });
  }
  const raw = await request.text();
  if (Buffer.byteLength(raw, "utf8") > MAX_BODY_BYTES) {
    return NextResponse.json({ ok: false, error: "payload_too_large" }, { status: 413, headers: CORS });
  }

  let body: RpcRequest;
  try {
    body = JSON.parse(raw) as RpcRequest;
  } catch {
    return rpcError(null, -32700, "Parse error");
  }
  const id = body.id;
  if (body.jsonrpc !== "2.0" || typeof body.method !== "string") {
    return rpcError(id, -32600, "Invalid Request");
  }
  if (id === undefined && body.method === "notifications/initialized") {
    return new NextResponse(null, { status: 202, headers: CORS });
  }
  if (body.method === "initialize") {
    return rpc(id, {
      protocolVersion: "2024-11-05",
      capabilities: { tools: {} },
      serverInfo: { name: "jarvis-obsidian-review-inbox", version: "1.0.0" },
    });
  }
  if (body.method === "ping") return rpc(id, {});
  if (body.method === "tools/list") {
    return rpc(id, {
      tools: [
        {
          name: "submit_daily_review",
          description:
            "日次レビューの確定時だけ使う。会話で確認できる範囲の生ログと、確定した戦術レビューを別々に送信してMacのObsidian保存待ち箱へ登録する。送信後は保存完了と断定せず、受付済みと伝える。",
          inputSchema: {
            type: "object",
            properties: {
              review_id: { type: "string", description: "再試行時も同じ値を使うUUID" },
              date: { type: "string", description: "レビュー日 YYYY-MM-DD（日本時間）" },
              raw_log: { type: "string", description: "今日のレビューの生ログ" },
              tactical_review: { type: "string", description: "結論と次の一手をまとめた戦術レビュー" },
            },
            required: ["review_id", "date", "raw_log", "tactical_review"],
            additionalProperties: false,
          },
        },
      ],
    });
  }
  if (body.method !== "tools/call") return rpcError(id, -32601, "Method not found");

  const params = body.params || {};
  if (params.name !== "submit_daily_review") return rpcError(id, -32601, "Unknown tool");
  const args = (params.arguments && typeof params.arguments === "object"
    ? params.arguments
    : {}) as Record<string, unknown>;
  const validated = validateDailyReview(args);
  if (!validated.ok) return rpc(id, { isError: true, content: [{ type: "text", text: validated.error }] });

  const supabase = createServiceClient();
  if (!supabase) {
    return rpc(id, { isError: true, content: [{ type: "text", text: "review inbox is not configured" }] });
  }
  let queued: { accepted: boolean; duplicate: boolean };
  try {
    queued = await enqueueDailyReview(supabase, validated.value);
  } catch (error) {
    const code = error instanceof Error ? error.message : "db_error";
    console.error("obsidian_review_submit_failed", code);
    return rpc(id, { isError: true, content: [{ type: "text", text: "review could not be queued" }] });
  }
  return rpc(id, {
    content: [{ type: "text", text: JSON.stringify({ ...queued, review_id: validated.value.review_id }) }],
  });
}
