/** タスク／ウォッチ「聞く」エンジン解決（Cloud → Gemini → ローカル） */

import {
  askWithCloudAgent,
  CLOUD_ASK_TIMEOUT_MS,
} from "@/lib/cursor/cloudAsk";
import { geminiReply } from "@/lib/geminiReply";
import type { AskEngine, AskVia } from "@/lib/askEngineTypes";
import { createHash } from "node:crypto";

// 短命・プロセス内のみ。権限確認後の利用者/対象スコープがない呼出は再利用しない。
const replyCache = new Map<string, { expires: number; result: AskResolveOk }>();

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

type AskCost = "free" | "flat" | "metered";
const COST_LABEL: Record<AskCost, string> = { free: "無料枠", flat: "定額枠内", metered: "従量" };

/** 契約で変わる費用区分は env で指定する。未設定・不明は従量扱い（安全側）。 */
function askCost(name: string): AskCost {
  const v = (process.env[name] || "").trim().toLowerCase();
  return v === "free" || v === "flat" ? v : "metered";
}

/** 「自動」で試す許可済み経路を、費用ゼロ→軽い→重い→従量の順に並べる */
export function autoRouteOrder(): { id: "gemini" | "cloud"; cost: AskCost; weight: number }[] {
  const routes: { id: "gemini" | "cloud"; cost: AskCost; weight: number }[] = [];
  if (process.env.ASK_AUTO_ALLOW_GEMINI === "1") routes.push({ id: "gemini", cost: askCost("ASK_COST_GEMINI"), weight: 0 });
  if (process.env.ASK_AUTO_ALLOW_CLOUD === "1") routes.push({ id: "cloud", cost: askCost("ASK_COST_CLOUD"), weight: 1 });
  const rank = (c: AskCost) => (c === "metered" ? 1 : 0);
  return routes.sort((a, b) => rank(a.cost) - rank(b.cost) || a.weight - b.weight);
}

/**
 * 選択エンジンに従い返答を得る。Cloud 選択時のみ Gemini へ自動フォールバック。
 */
export async function resolveAskReply(opts: {
  engine: AskEngine;
  prompt: string;
  cacheScope?: string;
}): Promise<AskResolveResult> {
  const started = Date.now();
  const cacheKey = opts.cacheScope ? createHash("sha256").update(JSON.stringify([
    opts.cacheScope, opts.engine, opts.prompt, process.env.GEMINI_MODEL,
    process.env.ASK_AUTO_ALLOW_GEMINI, process.env.ASK_AUTO_ALLOW_CLOUD,
    process.env.ASK_COST_GEMINI, process.env.ASK_COST_CLOUD,
  ])).digest("hex") : null;
  for (const [key, entry] of replyCache) if (entry.expires <= started) replyCache.delete(key);
  const cached = cacheKey ? replyCache.get(cacheKey) : undefined;
  let result: AskResolveResult;
  try {
    result = cached ? { ...cached.result, fallbackNotices: [...cached.result.fallbackNotices, "同じ入力への直近の回答を再利用しました"] } : await resolveAskReplyInternal(opts);
    if (!cached && cacheKey && result.ok) {
      if (replyCache.size >= 64) replyCache.delete(replyCache.keys().next().value!);
      replyCache.set(cacheKey, { expires: started + 60_000, result });
    }
  } catch {
    result = { ok: false, needLocal: true, error: "回答経路で予期しないエラーが発生しました", fallbackNotices: ["ローカルへ引き継いでください"] };
  }
  console.info(JSON.stringify({
    event: "ask_usage", version: 1, at: new Date().toISOString(),
    engine: opts.engine, via: result.ok ? result.via : "local_worker",
    outcome: result.ok ? "answered" : "handoff", input_chars: opts.prompt.length,
    cache_hit: Boolean(cached),
    elapsed_ms: Date.now() - started, tokens: null, cost: null,
    measurement: "tokens_and_cost_unavailable",
  }));
  return result;
}

async function resolveAskReplyInternal(opts: {
  engine: AskEngine;
  prompt: string;
}): Promise<AskResolveResult> {
  const notices: string[] = [];
  const prompt = opts.prompt;

  if (opts.engine === "auto") {
    // APIキーの存在は課金許可を意味しない。無料枠の有無も推測しない。
    // R4: 追加費用ゼロ（free/flat）→ 軽い順 → 重い → 従量 の順に試す（49_共通ルール）。
    for (const route of autoRouteOrder()) {
      const label = `${COST_LABEL[route.cost]}の${route.weight === 0 ? "軽量" : "高性能"}経路`;
      if (notices.length) notices.push(`次の経路へ上げます: ${label}`);
      if (route.id === "gemini") {
        const gem = await geminiReply(prompt, { maxAttempts: 1, timeoutMs: 20_000, maxOutputTokens: 2048 });
        if (gem.ok) return { ok: true, text: gem.text, via: "gemini", fallbackNotices: [...notices, `自動: 許可済みの${label}（Gemini）で回答しました`] };
        notices.push(`Geminiで回答できませんでした（${shortReason(gem.error)}）`);
      } else {
        const apiKey = (process.env.CURSOR_API_KEY || "").trim();
        if (!apiKey) continue;
        const cloud = await askWithCloudAgent({ apiKey, prompt, timeoutMs: CLOUD_ASK_TIMEOUT_MS });
        if (cloud.ok) return { ok: true, text: cloud.text, via: "cloud", fallbackNotices: [...notices, `自動: 許可済みの${label}（Cloud）で回答しました`] };
        notices.push(`Cloudで回答できませんでした（${shortReason(cloud.error)}）`);
      }
    }
    return { ok: false, needLocal: true, error: "自動回答できる許可済みAPIがないか、回答に失敗しました", fallbackNotices: [...notices, "ローカルの担当ツールへ引き継いでください。API課金と定額プランの利用枠は別です"] };
  }

  if (opts.engine === "cursor") {
    const apiKey = (process.env.CURSOR_API_KEY || "").trim();
    if (!apiKey) {
      notices.push(
        "Jarvis Cloud が使えなかったため（CURSOR_API_KEY 未設定）、Gemini に切り替えます",
      );
    } else {
      // 聞くは no-repo（CURSOR_CLOUD_REPO_URL があっても渡さない）
      const cloud = await askWithCloudAgent({
        apiKey,
        prompt,
        timeoutMs: CLOUD_ASK_TIMEOUT_MS,
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

    const gem = await geminiReply(prompt, { maxAttempts: 2, timeoutMs: 20_000, maxOutputTokens: 2048 });
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

  const gem = await geminiReply(prompt, { maxAttempts: 2, timeoutMs: 20_000, maxOutputTokens: 2048 });
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
