/**
 * FlowForge (AI Automation) read-only share proxy helpers.
 * Upstream rejects non-FlowForge Origins; we fetch server-side with Origin set.
 */
import { getAgentById, getAgentTeam } from "@/lib/agentTeam";

export const FLOWFORGE_BASE =
  process.env.FLOWFORGE_BASE_URL?.trim() ||
  "https://flowforge-259747770348.asia-northeast1.run.app";

const SHARE_ID_RE = /\/share\/([A-Za-z0-9_-]+)/;
const FLOW_ID_RE = /\/flows\/(flow_[A-Za-z0-9_-]+)/;

export type FlowforgeUpstreamResult =
  | { ok: true; status: number; body: unknown }
  | { ok: false; status: number; error: string; upstream?: string };

export function extractShareId(input: string): string | null {
  const t = input.trim();
  if (!t) return null;
  const m = SHARE_ID_RE.exec(t);
  if (m) return m[1];
  if (/^[A-Za-z0-9_-]{8,64}$/.test(t) && !t.startsWith("flow_")) return t;
  return null;
}

export function extractFlowId(input: string): string | null {
  const t = input.trim();
  if (!t) return null;
  const m = FLOW_ID_RE.exec(t);
  if (m) return m[1];
  if (/^flow_[A-Za-z0-9_-]+$/.test(t)) return t;
  return null;
}

/** Resolve shareId from share URL, flow URL/id, or agent id (111 / 312). */
export function resolveShareId(opts: {
  shareId?: string | null;
  url?: string | null;
  flowId?: string | null;
  agentId?: string | null;
}): { shareId: string } | { error: string; status: number } {
  if (opts.shareId) {
    const sid = extractShareId(opts.shareId);
    if (sid) return { shareId: sid };
    return { error: "invalid_share_id", status: 400 };
  }
  if (opts.url) {
    const sid = extractShareId(opts.url);
    if (sid) return { shareId: sid };
    const fid = extractFlowId(opts.url);
    if (fid) {
      const fromFlow = resolveShareIdFromFlowId(fid);
      if (fromFlow) return { shareId: fromFlow };
      return { error: "share_not_found_for_flow", status: 404 };
    }
    return { error: "url_must_contain_share_or_flow", status: 400 };
  }
  if (opts.flowId) {
    const fid = extractFlowId(opts.flowId);
    if (!fid) return { error: "invalid_flow_id", status: 400 };
    const sid = resolveShareIdFromFlowId(fid);
    if (!sid) return { error: "share_not_found_for_flow", status: 404 };
    return { shareId: sid };
  }
  if (opts.agentId) {
    const sid = resolveShareIdFromAgentId(opts.agentId.trim());
    if (!sid) return { error: "share_not_found_for_agent", status: 404 };
    return { shareId: sid };
  }
  return { error: "shareId_url_flowId_or_agentId_required", status: 400 };
}

function resolveShareIdFromFlowId(flowId: string): string | null {
  const hit = getAgentTeam().agents.find((a) => a.flowforge_id === flowId);
  if (hit?.flowforge_share_url) return extractShareId(hit.flowforge_share_url);
  return null;
}

function resolveShareIdFromAgentId(agentId: string): string | null {
  const hit = getAgentById(agentId);
  if (hit?.flowforge_share_url) return extractShareId(hit.flowforge_share_url);
  return null;
}

export function summarizeFlowPayload(payload: unknown): Record<string, unknown> {
  const root = (payload && typeof payload === "object" ? payload : {}) as {
    flow?: Record<string, unknown>;
  };
  const flow = (root.flow || {}) as {
    id?: string;
    name?: string;
    description?: string;
    updatedAt?: string;
    nodes?: Array<{ id?: string; data?: Record<string, unknown>; type?: string }>;
    edges?: unknown[];
  };
  const nodes = Array.isArray(flow.nodes) ? flow.nodes : [];
  const edges = Array.isArray(flow.edges) ? flow.edges : [];
  const kinds: Record<string, number> = {};
  const titles: Array<{ id: string; kind: string; title: string }> = [];
  for (const n of nodes) {
    const data = (n.data || {}) as Record<string, unknown>;
    const kind = String(data.kind || n.type || "?");
    kinds[kind] = (kinds[kind] || 0) + 1;
    titles.push({
      id: String(n.id || ""),
      kind,
      title: String(data.title || data.toolName || ""),
    });
  }
  return {
    id: flow.id ?? null,
    name: flow.name ?? null,
    description: flow.description ?? null,
    updatedAt: flow.updatedAt ?? null,
    node_count: nodes.length,
    edge_count: edges.length,
    kinds,
    nodes: titles,
  };
}

export async function fetchFlowforgeShare(
  shareId: string,
  opts?: { timeoutMs?: number },
): Promise<FlowforgeUpstreamResult> {
  const base = FLOWFORGE_BASE.replace(/\/$/, "");
  const url = `${base}/api/shares/${encodeURIComponent(shareId)}`;
  const timeoutMs = opts?.timeoutMs ?? 25_000;
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), timeoutMs);
  try {
    const res = await fetch(url, {
      method: "GET",
      headers: {
        Accept: "application/json",
        Origin: base,
        Referer: `${base}/share/${shareId}`,
        "User-Agent": "jarvis-flowforge-share-proxy/1.0",
      },
      signal: ctrl.signal,
      cache: "no-store",
    });
    const text = await res.text();
    let body: unknown = text;
    try {
      body = JSON.parse(text);
    } catch {
      /* keep text */
    }
    if (!res.ok) {
      return {
        ok: false,
        status: res.status >= 400 && res.status < 600 ? res.status : 502,
        error: "upstream_error",
        upstream: typeof body === "string" ? body.slice(0, 300) : JSON.stringify(body).slice(0, 300),
      };
    }
    return { ok: true, status: res.status, body };
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e);
    return { ok: false, status: 502, error: "upstream_fetch_failed", upstream: msg.slice(0, 300) };
  } finally {
    clearTimeout(timer);
  }
}

export function timingSafeEqual(a: string, b: string): boolean {
  if (a.length !== b.length) return false;
  let out = 0;
  for (let i = 0; i < a.length; i++) {
    out |= a.charCodeAt(i) ^ b.charCodeAt(i);
  }
  return out === 0;
}

/**
 * Auth for FlowForge read proxy / MCP.
 * Prefer Authorization: Bearer or x-flowforge-read-key.
 * ChatGPT カスタム MCP は Bearer UI が無いため、登録 URL の ?key= も可（認証なし接続用）。
 */
export function proxyAuthorized(
  headers: Headers,
  url?: URL | { searchParams: URLSearchParams },
): boolean {
  const expected = (process.env.FLOWFORGE_READ_PROXY_KEY || "").trim();
  if (!expected) return false;
  const fromHeader = (
    headers.get("authorization")?.replace(/^Bearer\s+/i, "") ||
    headers.get("x-flowforge-read-key") ||
    ""
  ).trim();
  const fromQuery = (
    url?.searchParams.get("key") ||
    url?.searchParams.get("api_key") ||
    ""
  ).trim();
  const got = fromHeader || fromQuery;
  return Boolean(got) && timingSafeEqual(got, expected);
}
