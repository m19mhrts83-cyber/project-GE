/**
 * Cursor Cloud Agent で方針相談・Q&A（タスク／ウォッチ用）。
 */

import { runCloudAgentPrompt, type CloudAgentResult } from "./cloudAgent";

function wrapAskPrompt(userPrompt: string): string {
  return [
    "あなたは Jarvis（秘書 AI）です。ユーザーのダッシュボード相談に日本語で答えてください。",
    "リポジトリやファイルは一切編集・作成しないでください。ツールで書き込まないでください。",
    "推測で事実を捏造しない。出力は返答本文のみ。前置き・説明・コードフェンスは付けない。",
    "",
    userPrompt.trim(),
  ].join("\n");
}

export async function askWithCloudAgent(opts: {
  apiKey: string;
  prompt: string;
  repoUrl?: string;
  timeoutMs?: number;
}): Promise<CloudAgentResult> {
  return runCloudAgentPrompt({
    apiKey: opts.apiKey,
    prompt: wrapAskPrompt(opts.prompt),
    name: "jarvis-dashboard-ask",
    repoUrl: opts.repoUrl,
    timeoutMs: opts.timeoutMs ?? 75_000,
    mode: "plan",
  });
}
