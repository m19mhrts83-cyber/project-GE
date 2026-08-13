/**
 * Cursor Cloud Agent で方針相談・Q&A（タスク／ウォッチ用）。
 *
 * 聞く用途は no-repo + agent モード固定。
 * plan＋リポ付きだと VM 起動・探索で 75s を超えやすい（2026-08 調査）。
 */

import {
  runCloudAgentPrompt,
  type CloudAgentMcpServer,
  type CloudAgentResult,
} from "./cloudAgent";

/** Vercel maxDuration(120) 内で Gemini フォールバック余地を残す */
export const CLOUD_ASK_TIMEOUT_MS = 90_000;

function wrapAskPrompt(userPrompt: string): string {
  return [
    "あなたは Jarvis（秘書 AI）です。ユーザーのダッシュボード相談に日本語で答えてください。",
    "リポジトリやファイルは一切編集・作成しないでください。ツールで書き込まないでください。",
    "読み取り専用のMCP/Web検索ツールが利用できる場合は、事実確認が必要なときだけ使ってください。",
    "推測で事実を捏造しない。出力は返答本文のみ。前置き・説明・コードフェンスは付けない。",
    "",
    userPrompt.trim(),
  ].join("\n");
}

function expandEnvPlaceholders(value: string): string {
  return value.replace(/\$\{([A-Z0-9_]+)\}/g, (_m, key: string) => {
    return process.env[key] || "";
  });
}

function stringRecord(v: unknown): Record<string, string> | undefined {
  if (!v || typeof v !== "object" || Array.isArray(v)) return undefined;
  const out: Record<string, string> = {};
  for (const [k, raw] of Object.entries(v)) {
    if (typeof raw === "string") {
      out[k] = expandEnvPlaceholders(raw);
    }
  }
  return Object.keys(out).length ? out : undefined;
}

function unwrapMcpJson(parsed: unknown): unknown {
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
    return parsed;
  }
  const row = parsed as Record<string, unknown>;
  if (row.mcpServers && typeof row.mcpServers === "object") {
    return row.mcpServers;
  }
  return parsed;
}

function normalizeMcpServer(
  v: unknown,
  nameFromKey?: string,
): CloudAgentMcpServer | null {
  if (!v || typeof v !== "object" || Array.isArray(v)) return null;
  const row = v as Record<string, unknown>;
  const name = (
    nameFromKey || (typeof row.name === "string" ? row.name : "")
  ).trim();
  if (!name) return null;
  const type =
    row.type === "http" || row.type === "sse" || row.type === "stdio"
      ? row.type
      : undefined;
  const url =
    typeof row.url === "string" ? expandEnvPlaceholders(row.url.trim()) : "";
  const command =
    typeof row.command === "string"
      ? expandEnvPlaceholders(row.command.trim())
      : "";
  if (!url && !command) return null;
  const args = Array.isArray(row.args)
    ? row.args
        .filter((a): a is string => typeof a === "string")
        .map(expandEnvPlaceholders)
    : undefined;
  const headers = stringRecord(row.headers);
  const env = stringRecord(row.env);
  return {
    name,
    type,
    ...(url ? { url } : {}),
    ...(command ? { command } : {}),
    ...(args?.length ? { args } : {}),
    ...(headers ? { headers } : {}),
    ...(env ? { env } : {}),
    ...(row.auth && typeof row.auth === "object" && !Array.isArray(row.auth)
      ? { auth: row.auth as Record<string, unknown> }
      : {}),
  };
}

function configuredAskMcpServers():
  | { ok: true; servers: CloudAgentMcpServer[] }
  | { ok: false; error: string } {
  const servers: CloudAgentMcpServer[] = [];
  const raw = (process.env.CURSOR_CLOUD_ASK_MCP_SERVERS_JSON || "").trim();
  if (raw) {
    let parsed: unknown;
    try {
      parsed = JSON.parse(raw);
    } catch (e) {
      return {
        ok: false,
        error: `CURSOR_CLOUD_ASK_MCP_SERVERS_JSON が JSON として読めません: ${
          e instanceof Error ? e.message : String(e)
        }`,
      };
    }
    const shape = unwrapMcpJson(parsed);
    if (Array.isArray(shape)) {
      for (const item of shape) {
        const server = normalizeMcpServer(item);
        if (server) servers.push(server);
      }
    } else if (shape && typeof shape === "object") {
      for (const [key, item] of Object.entries(shape)) {
        const server = normalizeMcpServer(item, key);
        if (server) servers.push(server);
      }
    } else {
      return {
        ok: false,
        error:
          "CURSOR_CLOUD_ASK_MCP_SERVERS_JSON は配列、または mcp.json 形式のオブジェクトで指定してください",
      };
    }
  }

  const tavilyEnabled =
    (process.env.CURSOR_CLOUD_ASK_ENABLE_TAVILY || "").trim() === "1";
  const tavilyKey = (process.env.TAVILY_API_KEY || "").trim();
  const hasTavily = servers.some((s) => s.name.toLowerCase() === "tavily");
  if (tavilyEnabled && tavilyKey && !hasTavily) {
    servers.push({
      name: "tavily",
      type: "http",
      url: "https://mcp.tavily.com/mcp",
      headers: { Authorization: `Bearer ${tavilyKey}` },
    });
  }

  return { ok: true, servers };
}

export async function askWithCloudAgent(opts: {
  apiKey: string;
  prompt: string;
  /** 無視する（聞くは常に no-repo）。互換のため残す */
  repoUrl?: string;
  timeoutMs?: number;
}): Promise<CloudAgentResult> {
  const mcp = configuredAskMcpServers();
  if (!mcp.ok) return { ok: false, error: mcp.error };
  return runCloudAgentPrompt({
    apiKey: opts.apiKey,
    prompt: wrapAskPrompt(opts.prompt),
    name: "jarvis-dashboard-ask",
    // 聞くはリポを付けない（CURSOR_CLOUD_REPO_URL が設定されていても無視）
    repoUrl: undefined,
    mcpServers: mcp.servers,
    timeoutMs: opts.timeoutMs ?? CLOUD_ASK_TIMEOUT_MS,
    mode: "agent",
  });
}
