/**
 * Cursor Cloud Agents API（共通）。
 * Auth: Basic（API key を username、password 空）
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

/**
 * Cloud Agent にプロンプトを投げ、timeoutMs 以内の結果を返す。
 */
export async function runCloudAgentPrompt(opts: {
  apiKey: string;
  prompt: string;
  name?: string;
  /** 任意。未指定なら no-repo agent */
  repoUrl?: string;
  timeoutMs?: number;
  mode?: "ask" | "plan" | "agent";
}): Promise<CloudAgentResult> {
  const apiKey = opts.apiKey.trim();
  if (!apiKey) return { ok: false, error: "CURSOR_API_KEY 未設定" };

  const timeoutMs = opts.timeoutMs ?? 75_000;
  const deadline = Date.now() + timeoutMs;
  const promptText = opts.prompt.trim();
  if (!promptText) return { ok: false, error: "プロンプトが空です" };

  const body: Record<string, unknown> = {
    prompt: { text: promptText },
    name: opts.name || "jarvis-cloud",
    mode: opts.mode || "plan",
  };
  const repo = (opts.repoUrl || "").trim();
  if (repo) {
    body.repos = [{ url: repo, startingRef: "main" }];
    body.autoCreatePR = false;
    body.skipReviewerRequest = true;
    body.workOnCurrentBranch = false;
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
    });
  } catch (e) {
    return {
      ok: false,
      error: `Cloud Agent 起動失敗: ${e instanceof Error ? e.message : String(e)}`,
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
    run?: { id?: string };
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

  while (Date.now() < deadline) {
    await sleep(2500);
    let runRes: Response;
    try {
      runRes = await fetch(`${API_BASE}/agents/${agentId}/runs/${runId}`, {
        headers: { Authorization: authHeader(apiKey) },
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
    let run: { status?: string; result?: string };
    try {
      run = JSON.parse(runText) as typeof run;
    } catch {
      return { ok: false, error: "Cloud run 応答が JSON ではありません" };
    }
    const st = (run.status || "").toUpperCase();
    if (st === "FINISHED") {
      const text = stripCloudFences(String(run.result || ""));
      if (!text) {
        return { ok: false, error: "Cloud Agent の結果が空です" };
      }
      return { ok: true, text, agentId, runId };
    }
    if (st === "ERROR" || st === "CANCELLED" || st === "EXPIRED") {
      return {
        ok: false,
        error: `Cloud Agent run ${st}: ${(run.result || "").slice(0, 160)}`,
      };
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
