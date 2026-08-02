/**
 * Cursor Cloud Agents API でメール下書きを見直す（本線）。
 * no-repo agent（repos 省略）で本文のみ返す。失敗時は呼び出し側で Mac キューへ。
 */

import { runCloudAgentPrompt } from "./cloudAgent";

export type CloudReviseOk = {
  ok: true;
  draft: string;
  agentId?: string;
  runId?: string;
};
export type CloudReviseErr = { ok: false; error: string };
export type CloudReviseResult = CloudReviseOk | CloudReviseErr;

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
  const r = await runCloudAgentPrompt({
    apiKey: opts.apiKey,
    prompt: buildCloudPrompt(opts.instruction, opts.draft),
    name: "jarvis-triage-revise",
    repoUrl: opts.repoUrl,
    timeoutMs: opts.timeoutMs,
    mode: "plan",
  });
  if (!r.ok) return r;
  return {
    ok: true,
    draft: r.text,
    agentId: r.agentId,
    runId: r.runId,
  };
}
