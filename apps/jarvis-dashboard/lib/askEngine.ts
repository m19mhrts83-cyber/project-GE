/** タスク／ウォッチ「聞く」エンジン解決（Cloud → Gemini → ローカル） */

import { askWithCloudAgent } from "@/lib/cursor/cloudAsk";
import { geminiReply } from "@/lib/geminiReply";
import type { AskEngine, AskVia } from "@/lib/askEngineTypes";

export type { AskEngine, AskVia } from "@/lib/askEngineTypes";

export type AskResolveOk = {
  ok: true;
  text: string;
  via: Exclude<AskVia, "local_worker">;
  fallbackNotices: string[];
  cloudError?: string;
};

export type AskResolveNeedLocal = {
  ok: false;
  needLocal: true;
  error: string;
  fallbackNotices: string[];
};

export type AskResolveResult = AskResolveOk | AskResolveNeedLocal;

function shortReason(err: string): string {
  const t = err.trim().replace(/\s+/g, " ");
  if (t.length <= 80) return t;
  return `${t.slice(0, 77)}…`;
}

/**
 * 選択エンジンに従い返答を得る。Cloud 選択時のみ Gemini へ自動フォールバック。
 */
export async function resolveAskReply(opts: {
  engine: AskEngine;
  prompt: string;
}): Promise<AskResolveResult> {
  const notices: string[] = [];
  const prompt = opts.prompt;

  if (opts.engine === "cursor") {
    const apiKey = (process.env.CURSOR_API_KEY || "").trim();
    if (!apiKey) {
      notices.push(
        "Jarvis Cloud が使えなかったため（CURSOR_API_KEY 未設定）、Gemini に切り替えます",
      );
    } else {
      const cloud = await askWithCloudAgent({
        apiKey,
        prompt,
        repoUrl: (process.env.CURSOR_CLOUD_REPO_URL || "").trim() || undefined,
        timeoutMs: 75_000,
      });
      if (cloud.ok) {
        return {
          ok: true,
          text: cloud.text,
          via: "cloud",
          fallbackNotices: notices,
        };
      }
      notices.push(
        `Jarvis Cloud が失敗したため、Gemini に切り替えます（${shortReason(cloud.error)}）`,
      );
    }

    const gem = await geminiReply(prompt);
    if (gem.ok) {
      notices.push("Gemini で答えました");
      return {
        ok: true,
        text: gem.text,
        via: "gemini",
        fallbackNotices: notices,
        cloudError: notices[0],
      };
    }
    notices.push(
      `Gemini も失敗したため、ローカル Cursor へ移ります（${shortReason(gem.error)}）`,
    );
    return {
      ok: false,
      needLocal: true,
      error: gem.error,
      fallbackNotices: notices,
    };
  }

  const gem = await geminiReply(prompt);
  if (gem.ok) {
    return {
      ok: true,
      text: gem.text,
      via: "gemini",
      fallbackNotices: notices,
    };
  }
  notices.push(
    `Gemini が失敗したため、ローカル Cursor へ移ります（${shortReason(gem.error)}）`,
  );
  return {
    ok: false,
    needLocal: true,
    error: gem.error,
    fallbackNotices: notices,
  };
}

export function formatAskReplyBody(
  text: string,
  via: Exclude<AskVia, "local_worker">,
  fallbackNotices: string[],
): string {
  const body = text.trim().slice(0, 2000);
  const fellBack = via === "gemini" && fallbackNotices.some((n) => /Cloud|切り替え/.test(n));
  if (via === "cloud") {
    return `〔via: Jarvis Cloud〕\n\n${body}`;
  }
  if (fellBack) {
    return `〔via: Gemini · Cloudから切替〕\n\n${body}`;
  }
  return `〔via: Gemini〕\n\n${body}`;
}

export function viaLabel(via: AskVia | null | undefined): string {
  if (via === "cloud") return "Jarvis Cloud";
  if (via === "gemini") return "Gemini";
  if (via === "local_worker") return "ローカル Cursor（Mac）";
  return "Jarvis";
}
