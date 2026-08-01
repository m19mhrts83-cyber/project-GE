/**
 * Cursor Cloud Agents API でメール下書きを見直す（本線）。
 * no-repo agent（repos 省略）で本文のみ返す。失敗時は呼び出し側で Mac キューへ。
 *
 * Auth: Basic（API key を username、password 空）— 公式 curl -u KEY:
 */

const API_BASE = "https://api.cursor.com/v1";

export type CloudReviseOk = { ok: true; draft: string; agentId?: string; runId?: string };
export type CloudReviseErr = { ok: false; error: string };
export type CloudReviseResult = CloudReviseOk | CloudReviseErr;

function authHeader(apiKey: string): string {
  // Basic: key as username, empty password
  return "Basic " + Buffer.from(`${apiKey}:`, "utf8").toString("base64");
}

function stripFences(text: string): string {
  let t = text.trim();
  if (t.startsWith("```")) {
    const lines = t.split("\n");
    if (lines[0]?.startsWith("```")) lines.shift();
    if (lines.length && lines[lines.length - 1]?.trim() === "```") lines.pop();
    t = lines.join("\n").trim();
  }
  return t.trim();
}

function buildCloudPrompt(instruction: string, draft: string): string {
  return [
    "あなたはビジネス日本語のメール下書き校正アシスタントです。",
    "リポジトリやファイルは一切編集・作成しないでください。ツールで書き込まないでください。",
    "意味は変えず、指示に従って返信下書きを書き直してください。",
    "出力は本文のみ（挨拶から結びまで）。前置き・説明・コードフェンスは付けない。",
    "",
    "【見直し指示】",
    instruction.trim() || "（丁寧に整えて）",
    "",
    "【現在の下書き】",
    draft,
  ].join("\n");
}

async function sleep(ms: number): Promise<void> {
  await new Promise((r) => setTimeout(r, ms));
}

/**
 * Cloud Agent で見直し。timeoutMs 以内に終わらなければ error。
 */
export async function reviseDraftWithCloudAgent(opts: {
  apiKey: string;
  instruction: string;
  draft: string;
  /** 任意。未指定なら no-repo agent */
  repoUrl?: string;
  timeoutMs?: number;
}): Promise<CloudReviseResult> {
  const apiKey = opts.apiKey.trim();
  if (!apiKey) return { ok: false, error: "CURSOR_API_KEY 未設定" };

  const timeoutMs = opts.timeoutMs ?? 75_000;
  const deadline = Date.now() + timeoutMs;
  const promptText = buildCloudPrompt(opts.instruction, opts.draft);

  const body: Record<string, unknown> = {
    prompt: { text: promptText },
    name: "jarvis-triage-revise",
    // ファイル編集を避けるため plan（読取・提案寄り）。本文は result に出る想定。
    mode: "plan",
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
      const draft = stripFences(String(run.result || ""));
      if (!draft) {
        return { ok: false, error: "Cloud Agent の結果が空です" };
      }
      return { ok: true, draft, agentId, runId };
    }
    if (st === "ERROR" || st === "CANCELLED" || st === "EXPIRED") {
      return {
        ok: false,
        error: `Cloud Agent run ${st}: ${(run.result || "").slice(0, 160)}`,
      };
    }
  }

  // タイムアウト: 可能ならキャンセル
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
    error: `Cloud Agent タイムアウト（${Math.round(timeoutMs / 1000)}秒）。Mac フォールバックへ。`,
  };
}
