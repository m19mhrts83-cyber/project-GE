/**
 * Cursor Cloud Agents API（共通）。
 * Auth: Basic（API key を username、password 空）
 *
 * 備考: POST /v1/agents は no-repo でも応答まで数十秒かかることがある
 *（完了待ちに近い挙動）。聞く用途は agent + no-repo、見直しは plan + repo 可。
 */

const API_BASE = "https://api.cursor.com/v1";

export type CloudAgentOk = {
  ok: true;
  text: string;
  agentId?: string;
  runId?: string;
};
export type CloudAgentErr = { ok: false; error: string };
export type CloudAgentResult = CloudAgentOk | CloudAgentErr;
export type CloudAgentMcpServer = {
  name: string;
  type?: "http" | "sse" | "stdio";
  url?: string;
  command?: string;
  args?: string[];
  headers?: Record<string, string>;
  env?: Record<string, string>;
  auth?: Record<string, unknown>;
};

/**
 * Cloud Agents REST `POST /v1/agents` の `mcpServers` は
 * `{ name, type?, url? | command?, ... }[]`。
 * SDK / `mcp.json` の名前キーオブジェクトとは別形。
 * @see https://cursor.com/docs/cloud-agent/api/endpoints
 */
export function toCloudAgentsRestMcpServers(
  servers: CloudAgentMcpServer[],
): CloudAgentMcpServer[] {
  const seen = new Set<string>();
  const out: CloudAgentMcpServer[] = [];
  for (const server of servers) {
    const name = server.name.trim();
    if (!name || seen.has(name)) continue;
    seen.add(name);
    const { name: _ignored, ...cfg } = server;
    out.push({ name, ...cfg });
  }
  return out;
}

function authHeader(apiKey: string): string {
  return "Basic " + Buffer.from(`${apiKey}:`, "utf8").toString("base64");
}

export function stripCloudFences(text: string): string {
  let t = text.trim();
  if (t.startsWith("```")) {
    const lines = t.split("\n");
    if (lines[0]?.startsWith("```")) lines.shift();
    if (lines.length && lines[lines.length - 1]?.trim() === "```") lines.pop();
    t = lines.join("\n").trim();
  }
  return t.trim();
}

async function sleep(ms: number): Promise<void> {
  await new Promise((r) => setTimeout(r, ms));
}

type RunSnapshot = { status?: string; result?: string };

function interpretRun(
  run: RunSnapshot,
  agentId: string,
  runId: string,
): CloudAgentResult | null {
  const st = (run.status || "").toUpperCase();
  if (st === "FINISHED" || st === "COMPLETED") {
    const text = stripCloudFences(String(run.result || ""));
    if (!text) {
      // create 応答では status=FINISHED でも result が無いことがある → 再ポーリング
      return null;
    }
    return { ok: true, text, agentId, runId };
  }
  if (st === "ERROR" || st === "CANCELLED" || st === "EXPIRED") {
    return {
      ok: false,
      error: `Cloud Agent run ${st}: ${(run.result || "").slice(0, 160)}`,
    };
  }
  return null;
}

/**
 * Cloud Agent にプロンプトを投げ、timeoutMs 以内の結果を返す。
 */
export async function runCloudAgentPrompt(opts: {
  apiKey: string;
  prompt: string;
  name?: string;
  /** 任意。未指定なら no-repo agent */
  repoUrl?: string;
  /** Inline MCP servers available to this run. */
  mcpServers?: CloudAgentMcpServer[];
  timeoutMs?: number;
  /** 既定 agent。聞く用途は agent、見直しは plan 可 */
  mode?: "plan" | "agent";
}): Promise<CloudAgentResult> {
  const apiKey = opts.apiKey.trim();
  if (!apiKey) return { ok: false, error: "CURSOR_API_KEY 未設定" };

  const timeoutMs = opts.timeoutMs ?? 75_000;
  const started = Date.now();
  const deadline = started + timeoutMs;
  const promptText = opts.prompt.trim();
  if (!promptText) return { ok: false, error: "プロンプトが空です" };

  const body: Record<string, unknown> = {
    prompt: { text: promptText },
    name: opts.name || "jarvis-cloud",
    mode: opts.mode || "agent",
  };
  const repo = (opts.repoUrl || "").trim();
  if (repo) {
    body.repos = [{ url: repo, startingRef: "main" }];
    body.autoCreatePR = false;
    body.skipReviewerRequest = true;
    body.workOnCurrentBranch = false;
  }
  const mcpServers = opts.mcpServers?.length
    ? toCloudAgentsRestMcpServers(opts.mcpServers)
    : [];
  if (mcpServers.length) {
    body.mcpServers = mcpServers;
  }

  let createRes: Response;
  try {
    createRes = await fetch(`${API_BASE}/agents`, {
      method: "POST",
      headers: {
        Authorization: authHeader(apiKey),
        "Content-Type": "application/json",
      },
      body: JSON.stringify(body),
      signal: AbortSignal.timeout(Math.max(5_000, timeoutMs)),
    });
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e);
    const timedOut =
      (e instanceof Error && e.name === "TimeoutError") ||
      /aborted|timeout/i.test(msg);
    return {
      ok: false,
      error: timedOut
        ? `Cloud Agent 起動タイムアウト（${Math.round(timeoutMs / 1000)}秒）`
        : `Cloud Agent 起動失敗: ${msg}`,
    };
  }

  const createText = await createRes.text();
  if (!createRes.ok) {
    return {
      ok: false,
      error: `Cloud Agent 起動 ${createRes.status}: ${createText.slice(0, 200)}`,
    };
  }

  let created: {
    agent?: { id?: string };
    id?: string;
    run?: { id?: string; status?: string; result?: string };
  };
  try {
    created = JSON.parse(createText) as typeof created;
  } catch {
    return { ok: false, error: "Cloud Agent 応答が JSON ではありません" };
  }

  const agentId = created.agent?.id || created.id;
  const runId = created.run?.id;
  if (!agentId || !runId) {
    return {
      ok: false,
      error: `Cloud Agent ID 不足: ${createText.slice(0, 200)}`,
    };
  }

  if (created.run) {
    const early = interpretRun(created.run, agentId, runId);
    if (early) return early;
  }

  // 初回は即ポーリング（create が FINISHED でも result 欠落のことがある）
  let first = true;
  while (Date.now() < deadline) {
    if (!first) {
      const remain = deadline - Date.now();
      if (remain <= 0) break;
      await sleep(Math.min(2000, Math.max(200, remain)));
    }
    first = false;

    let runRes: Response;
    try {
      runRes = await fetch(`${API_BASE}/agents/${agentId}/runs/${runId}`, {
        headers: { Authorization: authHeader(apiKey) },
        signal: AbortSignal.timeout(Math.max(3_000, deadline - Date.now())),
      });
    } catch (e) {
      return {
        ok: false,
        error: `Cloud poll 失敗: ${e instanceof Error ? e.message : String(e)}`,
      };
    }
    const runText = await runRes.text();
    if (!runRes.ok) {
      return {
        ok: false,
        error: `Cloud poll ${runRes.status}: ${runText.slice(0, 160)}`,
      };
    }
    let run: RunSnapshot;
    try {
      run = JSON.parse(runText) as RunSnapshot;
    } catch {
      return { ok: false, error: "Cloud run 応答が JSON ではありません" };
    }
    const decided = interpretRun(run, agentId, runId);
    if (decided) return decided;
    // FINISHED だが result 空 → 少し待って再取得
    const st = (run.status || "").toUpperCase();
    if (st === "FINISHED" || st === "COMPLETED") {
      await sleep(800);
      continue;
    }
  }

  try {
    await fetch(`${API_BASE}/agents/${agentId}/runs/${runId}/cancel`, {
      method: "POST",
      headers: { Authorization: authHeader(apiKey) },
    });
  } catch {
    /* ignore */
  }
  return {
    ok: false,
    error: `Cloud Agent タイムアウト（${Math.round(timeoutMs / 1000)}秒）`,
  };
}
