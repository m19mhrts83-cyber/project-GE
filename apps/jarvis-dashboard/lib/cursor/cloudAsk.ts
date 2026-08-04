/**
 * Cursor Cloud Agent で方針相談・Q&A（タスク／ウォッチ用）。
 *
 * 聞く用途は no-repo + agent モード固定。
 * plan＋リポ付きだと VM 起動・探索で 75s を超えやすい（2026-08 調査）。
 */

import { runCloudAgentPrompt, type CloudAgentResult } from "./cloudAgent";

/** Vercel maxDuration(120) 内で Gemini フォールバック余地を残す */
export const CLOUD_ASK_TIMEOUT_MS = 90_000;

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
  /** 無視する（聞くは常に no-repo）。互換のため残す */
  repoUrl?: string;
  timeoutMs?: number;
}): Promise<CloudAgentResult> {
  return runCloudAgentPrompt({
    apiKey: opts.apiKey,
    prompt: wrapAskPrompt(opts.prompt),
    name: "jarvis-dashboard-ask",
    // 聞くはリポを付けない（CURSOR_CLOUD_REPO_URL が設定されていても無視）
    repoUrl: undefined,
    timeoutMs: opts.timeoutMs ?? CLOUD_ASK_TIMEOUT_MS,
    mode: "agent",
  });
}
