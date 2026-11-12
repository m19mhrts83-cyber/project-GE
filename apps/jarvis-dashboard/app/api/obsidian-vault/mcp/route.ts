import { NextResponse, type NextRequest } from "next/server";
import { createServiceClient } from "@/lib/supabase/admin";
import { bearerMatches, isAllowedVaultPath, secretIsDistinct, validateReadRequest } from "@/lib/obsidianReviewAgent";

export const runtime = "nodejs";
export const maxDuration = 15;

const MAX_BODY_BYTES = 32 * 1024;
const CORS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
  "Access-Control-Allow-Headers": "Authorization, Content-Type, Accept, Mcp-Protocol-Version",
};

type RpcRequest = { jsonrpc?: string; id?: string | number | null; method?: string; params?: Record<string, unknown> };

function rpc(id: RpcRequest["id"], result: unknown) {
  return NextResponse.json({ jsonrpc: "2.0", id: id ?? null, result }, { headers: CORS });
}

function rpcError(id: RpcRequest["id"], code: number, message: string) {
  return NextResponse.json({ jsonrpc: "2.0", id: id ?? null, error: { code, message } }, { headers: CORS });
}

function toolText(id: RpcRequest["id"], text: string, isError = false) {
  return rpc(id, { ...(isError ? { isError: true } : {}), content: [{ type: "text", text }] });
}

export async function OPTIONS() {
  return new NextResponse(null, { status: 204, headers: CORS });
}

export async function GET(request: NextRequest) {
  if (!bearerMatches(request, "OBSIDIAN_REVIEW_READ_KEY", [
    "OBSIDIAN_REVIEW_SUBMIT_KEY", "OBSIDIAN_REVIEW_POLL_KEY", "OBSIDIAN_VAULT_POLL_KEY", "OBSIDIAN_REVIEW_MONITOR_KEY",
  ])) {
    return NextResponse.json({ ok: false, error: "unauthorized" }, { status: 401, headers: CORS });
  }
  return NextResponse.json(
    { ok: true, transport: "streamable-http", tools: ["search_vault_notes", "get_vault_read_result", "get_vault_note_excerpt"] },
    { headers: { ...CORS, "Cache-Control": "no-store" } },
  );
}

/** Read-only ChatGPT MCP. It can queue constrained requests but cannot write Vault files. */
export async function POST(request: NextRequest) {
  if (!bearerMatches(request, "OBSIDIAN_REVIEW_READ_KEY", [
    "OBSIDIAN_REVIEW_SUBMIT_KEY", "OBSIDIAN_REVIEW_POLL_KEY", "OBSIDIAN_VAULT_POLL_KEY", "OBSIDIAN_REVIEW_MONITOR_KEY",
  ])) {
    return NextResponse.json({ ok: false, error: "unauthorized" }, { status: 401, headers: CORS });
  }
  const raw = await request.text();
  if (Buffer.byteLength(raw, "utf8") > MAX_BODY_BYTES) return rpcError(null, -32600, "Request too large");
  let body: RpcRequest;
  try {
    body = JSON.parse(raw) as RpcRequest;
  } catch {
    return rpcError(null, -32700, "Parse error");
  }
  const id = body.id;
  if (body.jsonrpc !== "2.0" || typeof body.method !== "string") return rpcError(id, -32600, "Invalid Request");
  if (id === undefined && body.method === "notifications/initialized") return new NextResponse(null, { status: 202, headers: CORS });
  if (body.method === "initialize") {
    return rpc(id, {
      protocolVersion: "2024-11-05",
      capabilities: { tools: {} },
      serverInfo: { name: "jarvis-obsidian-vault-read", version: "1.0.0" },
    });
  }
  if (body.method === "ping") return rpc(id, {});
  if (body.method === "tools/list") {
    return rpc(id, {
      tools: [
        {
          name: "search_vault_notes",
          description: "許可されたObsidian JournalとPermanent NoteだけをMacで検索する。日付指定、直近7日/30日、テーマ検索に使う。返されたrequest_idをget_vault_read_resultへ渡し、完了結果の出典・抜粋を取得する。検索結果は短い抜粋のみ。",
          inputSchema: {
            type: "object",
            properties: {
              query: { type: "string", description: "任意。人物・案件・テーマ名など。日付ログだけなら省略可" },
              date: { type: "string", description: "指定日 JST、YYYY-MM-DD" },
              from_date: { type: "string", description: "期間の開始日 JST、YYYY-MM-DD" },
              to_date: { type: "string", description: "終了日 JST、YYYY-MM-DD" },
              days: { type: "integer", enum: [7, 30], description: "直近7日または30日" },
              limit: { type: "integer", minimum: 1, maximum: 10, description: "最大結果数（既定6）" },
            },
            required: [],
            additionalProperties: false,
          },
        },
        {
          name: "get_vault_read_result",
          description: "search_vault_notesで返されたrequest_idを使い、Mac側検索の状態または出典付き結果を取得する。pendingなら数秒後に再確認する。",
          inputSchema: {
            type: "object",
            properties: { request_id: { type: "string", description: "前の検索ツールが返したUUID" } },
            required: ["request_id"],
            additionalProperties: false,
          },
        },
        {
          name: "get_vault_note_excerpt",
          description: "検索結果のsource_pathを指定し、許可フォルダ内のノートまたは見出し部分だけを追加取得する。返されたrequest_idをget_vault_read_resultへ渡す。",
          inputSchema: {
            type: "object",
            properties: {
              source_path: { type: "string", description: "検索結果に含まれるVault相対パス" },
              heading: { type: "string", description: "任意の見出し名" },
            },
            required: ["source_path"],
            additionalProperties: false,
          },
        },
      ],
    });
  }
  if (body.method !== "tools/call") return rpcError(id, -32601, "Method not found");

  const params = body.params || {};
  const name = params.name;
  const args = (params.arguments && typeof params.arguments === "object" ? params.arguments : {}) as Record<string, unknown>;
  const supabase = createServiceClient();
  if (!supabase) return toolText(id, "Obsidian read queue is not configured", true);
  if (!secretIsDistinct("OBSIDIAN_VAULT_POLL_KEY", [
    "OBSIDIAN_REVIEW_SUBMIT_KEY", "OBSIDIAN_REVIEW_POLL_KEY", "OBSIDIAN_REVIEW_READ_KEY", "OBSIDIAN_REVIEW_MONITOR_KEY",
  ])) {
    return toolText(id, "Mac Vault read relay is not configured with its own poll key", true);
  }

  if (name === "get_vault_read_result") {
    const requestId = typeof args.request_id === "string" ? args.request_id.trim() : "";
    if (!/^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(requestId)) {
      return toolText(id, "request_id must be a UUID", true);
    }
    const { data, error } = await supabase
      .from("obsidian_vault_read_requests")
      .select("status,result,error_code,expires_at")
      .eq("id", requestId)
      .maybeSingle();
    if (error) return toolText(id, "Could not read the request status", true);
    if (!data || Date.parse(data.expires_at) < Date.now()) return toolText(id, JSON.stringify({ status: "expired", request_id: requestId }));
    if (data.status === "completed") return toolText(id, JSON.stringify({ status: "completed", request_id: requestId, result: data.result }));
    if (data.status === "failed") return toolText(id, JSON.stringify({ status: "failed", request_id: requestId, error: data.error_code || "read_failed" }));
    return toolText(id, JSON.stringify({ status: "pending", request_id: requestId, retry_after_seconds: 5 }));
  }

  let requested: ReturnType<typeof validateReadRequest>;
  if (name === "search_vault_notes") {
    requested = validateReadRequest({ ...args, type: "search" });
  } else if (name === "get_vault_note_excerpt") {
    requested = validateReadRequest({ ...args, type: "excerpt" });
  } else {
    return toolText(id, "Unknown read-only tool", true);
  }
  if (!requested.ok) return toolText(id, requested.error, true);
  if (requested.requestType === "excerpt" && !isAllowedVaultPath(String(requested.payload.source_path || ""))) {
    return toolText(id, "source_path is outside the read allowlist", true);
  }

  // Remove stale requests opportunistically; the queue is a temporary relay, not an index.
  await supabase.from("obsidian_vault_read_requests").delete().lt("expires_at", new Date().toISOString());
  const { count: pendingCount, error: countError } = await supabase
    .from("obsidian_vault_read_requests")
    .select("id", { count: "exact", head: true })
    .in("status", ["pending", "processing"])
    .gt("expires_at", new Date().toISOString());
  if (countError || (pendingCount ?? 0) >= 10) return toolText(id, "Vault read queue is busy; retry shortly", true);
  const { data: queued, error } = await supabase
    .from("obsidian_vault_read_requests")
    .insert({ request_type: requested.requestType, request_payload: requested.payload })
    .select("id")
    .single();
  if (error || !queued) return toolText(id, "Could not queue the Vault read request", true);
  return toolText(id, JSON.stringify({ status: "queued", request_id: queued.id, poll_tool: "get_vault_read_result" }));
}
